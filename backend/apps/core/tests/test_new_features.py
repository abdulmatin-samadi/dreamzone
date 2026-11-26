from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import LoginSession, Role
from apps.academics.models import Group
from apps.audit.models import AuditLog
from apps.core.tests.helpers import PASSWORD, answer_all, client_for, make_exam, make_levels, make_student, make_user
from apps.examinations.models import ExamAttempt, ExaminationVariant, VariantQuestion
from apps.examinations.services import create_assignments, start_attempt
from apps.questions.models import Question, QuestionType, Section
from apps.students.models import StudentGroup

API = "/api/v1"


def login(username, device="dev-a", ua="Mozilla/5.0 (Windows NT 10.0) Chrome/120.0 Safari/537.36"):
    c = APIClient(HTTP_USER_AGENT=ua, HTTP_X_DEVICE_ID=device)
    r = c.post(f"{API}/auth/login/", {"username": username, "password": PASSWORD}, format="json")
    assert r.status_code == 200, r.content
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {r.json()['access']}")
    return c, r.json()


class SessionTests(TestCase):
    def setUp(self):
        cache.clear()
        make_levels()
        self.user = make_user("ali", Role.TEACHER)
        self.admin = make_user("boss", Role.ADMIN)

    def test_list_and_sign_out_other_devices(self):
        a, _ = login("ali", "dev-a")
        b, tokens_b = login("ali", "dev-b", ua="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) Safari/604.1")
        rows = a.get(f"{API}/auth/sessions/").json()
        self.assertEqual(len(rows), 2)
        self.assertEqual(sum(r["current"] for r in rows), 1)
        self.assertIn("Safari · iPhone", [r["device"] for r in rows])
        self.assertEqual(a.post(f"{API}/auth/sessions/revoke-others/").json()["revoked"], 1)
        self.assertEqual(b.get(f"{API}/auth/me/").status_code, 401)            # signed out at once
        self.assertEqual(APIClient().post(f"{API}/auth/refresh/", {"refresh": tokens_b["refresh"]}, format="json").status_code, 401)
        self.assertEqual(a.get(f"{API}/auth/me/").status_code, 200)            # this device stays
        self.assertTrue(AuditLog.objects.filter(action="session.revoked_all").exists())

    def test_refresh_keeps_the_session_and_logout_revokes_it(self):
        a, t = login("ali")
        r = APIClient().post(f"{API}/auth/refresh/", {"refresh": t["refresh"]}, format="json")
        self.assertEqual(r.status_code, 200)
        a2 = APIClient()
        a2.credentials(HTTP_AUTHORIZATION=f"Bearer {r.json()['access']}")
        self.assertEqual(a2.get(f"{API}/auth/me/").status_code, 200)
        a2.post(f"{API}/auth/logout/", {"refresh": r.json()["refresh"]}, format="json")
        self.assertEqual(a.get(f"{API}/auth/me/").status_code, 401)
        self.assertFalse(LoginSession.objects.filter(revoked_at__isnull=True).exists())

    def test_admin_signs_a_user_out_everywhere_and_password_reset_does_too(self):
        a, _ = login("ali")
        admin = client_for(self.admin)
        self.assertEqual(len(admin.get(f"{API}/users/{self.user.id}/sessions/").json()), 1)
        self.assertEqual(admin.post(f"{API}/users/{self.user.id}/logout-all/").json()["revoked"], 1)
        self.assertEqual(a.get(f"{API}/auth/me/").status_code, 401)
        b, _ = login("ali")
        admin.post(f"{API}/users/{self.user.id}/reset-password/")
        self.assertEqual(b.get(f"{API}/auth/me/").status_code, 401)
        self.assertTrue(AuditLog.objects.filter(action="user.password_reset", target_id=str(self.user.id)).exists())
        self.assertEqual(client_for(self.user).get(f"{API}/users/{self.user.id}/sessions/").status_code, 403)


class OneDeviceTests(TestCase):
    def setUp(self):
        self.L = make_levels()
        self.admin = make_user("admin", Role.ADMIN)
        self.desk = make_user("desk", Role.RECEPTIONIST)
        self.student = make_student("stu", self.L["A1"])
        self.exam, _ = make_exam(self.L["A1"], creator=self.admin)
        create_assignments(examination=self.exam, students=[self.student], assigned_by=self.admin)
        self.assignment = self.student.assignments.get()

    def dev(self, device):
        c = client_for(self.student.user)
        c.credentials(HTTP_X_DEVICE_ID=device, HTTP_X_DEVICE_NAME="Kompyuter%203", HTTP_USER_AGENT="Mozilla/5.0 (Windows NT 10.0) Chrome/120.0")
        return c

    def test_second_device_is_refused_until_staff_release_it(self):
        a, b = self.dev("device-a"), self.dev("device-b")
        r = a.post(f"{API}/assignments/{self.assignment.id}/start/")
        self.assertEqual(r.status_code, 200, r.content)
        attempt_id = r.json()["id"] if "id" in r.json() else ExamAttempt.objects.get().id
        att = ExamAttempt.objects.get(pk=attempt_id)
        self.assertEqual(att.device_id, "device-a")
        self.assertEqual(att.device_label, "Kompyuter 3 — Chrome · Windows")
        self.assertEqual(b.post(f"{API}/assignments/{self.assignment.id}/start/").json()["code"], "attempt_other_device")
        self.assertEqual(b.get(f"{API}/attempts/{attempt_id}/").status_code, 409)
        self.assertEqual(b.post(f"{API}/attempts/{attempt_id}/submit/").status_code, 409)
        self.assertEqual(a.get(f"{API}/attempts/{attempt_id}/").status_code, 200)

        live = client_for(self.desk).get(f"{API}/live-attempts/").json()["attempts"]
        self.assertEqual(len(live), 1)
        self.assertEqual((live[0]["device"], live[0]["online"], live[0]["answered"]), ("Kompyuter 3 — Chrome · Windows", True, 0))

        self.assertEqual(client_for(self.desk).post(f"{API}/live-attempts/{attempt_id}/release-device/").status_code, 200)
        self.assertEqual(b.get(f"{API}/attempts/{attempt_id}/").status_code, 200)   # b now owns it
        self.assertEqual(a.get(f"{API}/attempts/{attempt_id}/").status_code, 409)
        self.assertTrue(AuditLog.objects.filter(action="attempt.device_released").exists())

    def test_live_list_is_staff_only(self):
        self.assertEqual(client_for(self.student.user).get(f"{API}/live-attempts/").status_code, 403)
        self.assertEqual(client_for(make_user("t", Role.TEACHER)).get(f"{API}/live-attempts/").status_code, 403)


class AuditTests(TestCase):
    def setUp(self):
        self.L = make_levels()
        self.admin = make_user("admin", Role.ADMIN)

    def test_actions_are_logged_and_only_admin_reads_them(self):
        st = make_student("stu", self.L["A1"])
        admin = client_for(self.admin)
        admin.post(f"{API}/students/{st.id}/set-level/", {"level": self.L["B1"].id, "note": "ok"}, format="json")
        admin.delete(f"{API}/students/{st.id}/")
        rows = admin.get(f"{API}/audit-log/").json()["results"]
        self.assertEqual([r["action"] for r in rows], ["student.deleted", "student.level_changed"])
        self.assertEqual(rows[1]["detail"]["to"], "B1")
        self.assertEqual(rows[0]["actor_name"], self.admin.full_name)
        self.assertEqual(admin.get(f"{API}/audit-log/", {"action": "student.level"}).json()["count"], 1)
        self.assertEqual(admin.get(f"{API}/audit-log/", {"search": "Stu"}).json()["count"], 2)
        self.assertIn("student.deleted", admin.get(f"{API}/audit-actions/").json())
        self.assertEqual(client_for(make_user("desk", Role.RECEPTIONIST)).get(f"{API}/audit-log/").status_code, 403)


class TeacherToolsTests(TestCase):
    def setUp(self):
        self.L = make_levels()
        self.admin = make_user("admin", Role.ADMIN)
        self.teacher = make_user("teach", Role.TEACHER)
        self.group = Group.objects.create(name="G1", level=self.L["A1"], teacher=self.teacher.teacher_profile)

    def sit(self, student, exam, correct):
        create_assignments(examination=exam, students=[student], assigned_by=self.admin)
        a = start_attempt(assignment_id=student.assignments.get(examination=exam).id, student=student, started_by=student.user)
        c = client_for(student.user)
        answer_all(c, a.id, correct_count=correct)
        c.post(f"{API}/attempts/{a.id}/submit/")

    def test_ranking_and_top_growers(self):
        s1, s2, s3 = (make_student(n, self.L["A1"]) for n in ("one", "two", "three"))
        for s in (s1, s2, s3):
            StudentGroup.objects.create(student=s, group=self.group)
        e1, _ = make_exam(self.L["A1"], kind="UPGRADE", target=self.L["A2"], creator=self.teacher, n=4)
        e2, _ = make_exam(self.L["A2"], kind="UPGRADE", target=self.L["B1"], creator=self.teacher, n=4)
        self.sit(s1, e1, 1)
        self.sit(s1, e2, 4)   # 25 % -> 100 %
        self.sit(s2, e1, 3)   # 75 %
        r = client_for(self.teacher).get(f"{API}/groups/{self.group.id}/ranking/").json()
        names = [x["name"] for x in r["students"]]
        self.assertEqual(names[:2], [s1.user.full_name, s2.user.full_name])
        top = r["students"][0]
        self.assertEqual((top["rank"], top["latest"], top["growth"], top["top_grower"]), (1, 100.0, 75.0, True))
        self.assertFalse(r["students"][1]["top_grower"])
        self.assertIsNone(r["students"][2]["rank"])  # no exams yet
        other = make_user("t2", Role.TEACHER)
        self.assertEqual(client_for(other).get(f"{API}/groups/{self.group.id}/ranking/").status_code, 404)
        self.assertEqual(client_for(s1.user).get(f"{API}/groups/{self.group.id}/ranking/").status_code, 403)

    def test_writing_queue(self):
        st = make_student("stu", self.L["A1"])
        StudentGroup.objects.create(student=st, group=self.group)
        exam, variant = make_exam(self.L["A1"], kind="UPGRADE", target=self.L["A2"], creator=self.teacher, n=1)
        w = Question.objects.create(text="Write about you.", question_type=QuestionType.WRITING, section=Section.WRITING,
                                    level=self.L["A1"], points=10, created_by=self.admin)
        VariantQuestion.objects.create(variant=variant, question=w, order=1)
        create_assignments(examination=exam, students=[st], assigned_by=self.admin)
        a = start_attempt(assignment_id=st.assignments.get().id, student=st, started_by=st.user)
        c = client_for(st.user)
        c.put(f"{API}/attempts/{a.id}/answers/", {"answers": [{"question_id": w.id, "answer": {"text": "I am a student here."}}]}, format="json")
        c.post(f"{API}/attempts/{a.id}/submit/")
        tc = client_for(self.teacher)
        q = tc.get(f"{API}/results/writing-queue/").json()
        self.assertEqual(len(q), 1)
        self.assertEqual((q[0]["writing"][0]["text"], q[0]["writing"][0]["words"]), ("I am a student here.", 5))
        tc.post(f"{API}/results/{q[0]['id']}/grade-writing/", {"grades": [{"question_id": w.id, "points": 6}]}, format="json")
        self.assertEqual(tc.get(f"{API}/results/writing-queue/").json(), [])
        self.assertTrue(AuditLog.objects.filter(action="result.writing_graded").exists())
        self.assertEqual(c.get(f"{API}/results/writing-queue/").status_code, 403)

    def test_duplicate_variant_copies_questions(self):
        exam, variant = make_exam(self.L["A1"], kind="UPGRADE", target=self.L["A2"], creator=self.teacher, n=3)
        r = client_for(self.teacher).post(f"{API}/variants/{variant.id}/duplicate/")
        self.assertEqual(r.status_code, 201, r.content)
        new = ExaminationVariant.objects.get(pk=r.json()["id"])
        self.assertEqual(new.name, "B")
        old_q = list(variant.questions.order_by("variant_links__order"))
        new_q = list(new.questions.order_by("variant_links__order"))
        self.assertEqual([q.text for q in new_q], [q.text for q in old_q])
        self.assertTrue(set(q.id for q in new_q).isdisjoint(q.id for q in old_q))     # real copies
        self.assertEqual([o.text for o in new_q[0].options.all()], ["right", "wrong"])
        self.assertEqual(client_for(make_user("t2", Role.TEACHER)).post(f"{API}/variants/{variant.id}/duplicate/").status_code, 404)


class MonthlyReportTests(TestCase):
    def setUp(self):
        self.L = make_levels()
        self.admin = make_user("admin", Role.ADMIN)
        self.desk = make_user("desk", Role.RECEPTIONIST)

    def test_report_numbers_and_files(self):
        from django.utils import timezone

        st = make_student("stu", None)
        exam, _ = make_exam(self.L["A1"], creator=self.admin, n=4)
        create_assignments(examination=exam, students=[st], assigned_by=self.admin)
        a = start_attempt(assignment_id=st.assignments.get().id, student=st, started_by=st.user)
        c = client_for(st.user)
        answer_all(c, a.id, correct_count=3)
        c.post(f"{API}/attempts/{a.id}/submit/")
        StudentGroup.objects.create(student=st, group=Group.objects.create(name="G", level=self.L["A1"]))
        month = timezone.localdate().strftime("%Y-%m")
        d = client_for(self.desk).get(f"{API}/analytics/monthly/", {"month": month}).json()
        self.assertEqual(d["totals"]["placement_tests"], 1)
        self.assertEqual(d["totals"]["joined_group"], 1)
        self.assertEqual(d["totals"]["new_students"], 1)
        self.assertEqual(d["by_level"][0]["placement_tests"], 1)
        x = client_for(self.admin).get(f"{API}/analytics/monthly/", {"month": month, "file": "xlsx"})
        self.assertEqual(x.status_code, 200)
        self.assertTrue(x.content.startswith(b"PK"))
        p = client_for(self.admin).get(f"{API}/analytics/monthly/", {"month": month, "file": "pdf"})
        self.assertTrue(p.content.startswith(b"%PDF"))
        self.assertEqual(client_for(self.admin).get(f"{API}/analytics/monthly/", {"month": "2026-13"}).status_code, 400)
        self.assertEqual(client_for(make_user("t", Role.TEACHER)).get(f"{API}/analytics/monthly/").status_code, 403)
