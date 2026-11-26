from django.test import TestCase

from apps.accounts.models import Role
from apps.academics.models import Group
from apps.core.tests.helpers import answer_all, client_for, make_levels, make_student, make_user
from apps.results.models import ApprovalStatus, ExamResult
from apps.students.models import LevelChangeHistory, StudentGroup, StudentProfile

API = "/api/v1"


class UpgradeFlowTests(TestCase):
    def setUp(self):
        self.L = make_levels()
        self.admin = make_user("admin", Role.ADMIN)
        self.teacher = make_user("teach", Role.TEACHER)
        self.other_teacher = make_user("teach2", Role.TEACHER)
        self.group = Group.objects.create(name="G1", level=self.L["B1"], teacher=self.teacher.teacher_profile)
        self.s1, self.s2 = make_student("s1", self.L["B1"]), make_student("s2", self.L["B1"])
        self.s_other_level = make_student("s3", self.L["A2"])
        for s in (self.s1, self.s2, self.s_other_level):
            StudentGroup.objects.create(student=s, group=self.group)
        self.tc = client_for(self.teacher)

    def build_exam(self, n=4, passing=2.4):  # points: 60% of 4
        exam = self.tc.post(f"{API}/examinations/", {
            "kind": "UPGRADE", "title": "B1 -> B2", "level": self.L["B1"].id, "target_level": self.L["B2"].id,
            "duration_minutes": 30, "passing_score": passing}).json()
        variant = self.tc.post(f"{API}/variants/", {"examination": exam["id"], "name": "A"}).json()
        qids = []
        for i in range(n):
            r = self.tc.post(f"{API}/questions/", {
                "text": f"Q{i}", "question_type": "MCQ", "section": "GRAMMAR", "level": self.L["B2"].id, "points": 1,
                "options": [{"text": "right", "is_correct": True}, {"text": "wrong", "is_correct": False}]})
            self.assertEqual(r.status_code, 201, r.content)
            qids.append(r.json()["id"])
        r = self.tc.put(f"{API}/variants/{variant['id']}/questions/", {"question_ids": qids})
        self.assertEqual(r.status_code, 200, r.content)
        # cannot assign before publishing
        self.assertEqual(self.tc.post(f"{API}/examinations/{exam['id']}/assign/", {"group_ids": [self.group.id]}).status_code, 409)
        self.assertEqual(self.tc.post(f"{API}/examinations/{exam['id']}/publish/").status_code, 200)
        return exam, variant

    def assign_group(self, exam):
        r = self.tc.post(f"{API}/examinations/{exam['id']}/assign/", {"group_ids": [self.group.id]})
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()

    def sit(self, student, correct):
        c = client_for(student.user)
        a = c.get(f"{API}/my/assignments/").json()[0]
        attempt = c.post(f"{API}/assignments/{a['id']}/start/").json()
        answer_all(c, attempt["id"], correct_count=correct)
        rid = c.post(f"{API}/attempts/{attempt['id']}/submit/").json()["result_id"]
        return c, a, rid

    def test_group_assignment_skips_students_from_other_level(self):
        exam, _ = self.build_exam()
        out = self.assign_group(exam)
        self.assertEqual(out["created"], 2)
        self.assertEqual(len(out["skipped_level_mismatch"]), 1)
        self.assertEqual(self.assign_group(exam)["skipped_existing"], 2)  # no duplicates

    def test_pass_then_teacher_approval_moves_student_up(self):
        exam, _ = self.build_exam()
        self.assign_group(exam)
        c, a, rid = self.sit(self.s1, correct=3)
        res = ExamResult.objects.get(pk=rid)
        self.assertEqual(res.approval_status, ApprovalStatus.PENDING)
        self.assertEqual(StudentProfile.objects.get(pk=self.s1.pk).current_level.code, "B1")  # unchanged so far

        detail = c.get(f"{API}/results/{rid}/").json()
        self.assertIsNone(detail["answers"])  # key hidden from the student
        self.assertEqual(c.post(f"{API}/results/{rid}/approve/").status_code, 403)  # student cannot approve

        r = self.tc.post(f"{API}/results/{rid}/approve/", {"note": "well done"})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(StudentProfile.objects.get(pk=self.s1.pk).current_level.code, "B2")
        h = LevelChangeHistory.objects.get(student=self.s1)
        self.assertEqual((h.from_level.code, h.to_level.code, h.reason, h.changed_by), ("B1", "B2", "UPGRADE", self.teacher))

        # locked: the teacher cannot touch it again, the admin can override and the level is reverted
        self.assertEqual(self.tc.post(f"{API}/results/{rid}/reject/").json()["code"], "result_locked")
        self.assertEqual(self.tc.post(f"{API}/results/{rid}/override/", {"status": "REJECTED", "note": "x"}).status_code, 403)
        ac = client_for(self.admin)
        r = ac.post(f"{API}/results/{rid}/override/", {"status": "REJECTED", "note": "cheating suspected"})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(StudentProfile.objects.get(pk=self.s1.pk).current_level.code, "B1")
        self.assertEqual(LevelChangeHistory.objects.filter(student=self.s1).count(), 2)

    def test_failing_student_keeps_level_and_cannot_retry(self):
        exam, _ = self.build_exam()
        self.assign_group(exam)
        c, a, rid = self.sit(self.s2, correct=1)
        res = ExamResult.objects.get(pk=rid)
        self.assertFalse(res.passed)  # below the pass mark: only the system's suggestion
        self.assertEqual(res.approval_status, ApprovalStatus.PENDING)  # the teacher still decides
        self.assertIsNone(c.get(f"{API}/results/{rid}/").json()["passed"])  # student: "result awaited"
        self.assertTrue(self.tc.get(f"{API}/results/{rid}/").json()["passed"] is False)  # teacher sees the suggestion
        self.assertEqual(self.tc.post(f"{API}/results/{rid}/reject/", {"note": "Again next month"}).status_code, 200)
        self.assertFalse(c.get(f"{API}/results/{rid}/").json()["passed"])  # now decided: not passed
        self.assertEqual(StudentProfile.objects.get(pk=self.s2.pk).current_level.code, "B1")
        r = c.post(f"{API}/assignments/{a['id']}/start/")
        self.assertEqual((r.status_code, r.json()["code"]), (409, "attempt_already_finished"))
        listed = c.get(f"{API}/my/assignments/").json()[0]
        self.assertEqual(listed["state"], "completed")

    def test_teacher_isolation(self):
        exam, _ = self.build_exam()
        self.assign_group(exam)
        _, _, rid = self.sit(self.s1, correct=4)
        oc = client_for(self.other_teacher)
        self.assertEqual(oc.get(f"{API}/results/").json()["count"], 0)
        self.assertEqual(oc.get(f"{API}/results/{rid}/").status_code, 404)
        self.assertEqual(oc.post(f"{API}/results/{rid}/approve/").status_code, 404)
        self.assertEqual(oc.get(f"{API}/examinations/{exam['id']}/").status_code, 404)
        self.assertEqual(oc.get(f"{API}/students/").json()["count"], 0)
        # cannot assign to someone else's group / students
        r = oc.post(f"{API}/examinations/{exam['id']}/assign/", {"student_ids": [self.s1.id]})
        self.assertEqual(r.status_code, 404)

    def test_students_cannot_use_staff_endpoints(self):
        sc = client_for(self.s1.user)
        for method, url in [("get", "/users/"), ("post", "/examinations/"), ("get", "/questions/"),
                            ("post", "/variants/"), ("get", "/analytics/results-summary/"), ("get", "/results/export/")]:
            self.assertIn(getattr(sc, method)(f"{API}{url}").status_code, (403, 404), url)

    def test_variants_manual_and_random_assignment(self):
        exam, v1 = self.build_exam()
        v2 = self.tc.post(f"{API}/variants/", {"examination": exam["id"], "name": "B"}).json()
        q = self.tc.get(f"{API}/variants/{v1['id']}/").json()["questions"]
        self.tc.put(f"{API}/variants/{v2['id']}/questions/", {"question_ids": [x["question"] for x in q][:2]})
        r = self.tc.post(f"{API}/examinations/{exam['id']}/assign/", {"student_ids": [self.s1.id], "variant": v2["id"]})
        self.assertEqual(r.status_code, 201, r.content)
        assignment = self.tc.get(f"{API}/assignments/?student={self.s1.id}").json()["results"][0]
        self.assertEqual(assignment["variant"], v2["id"])
        # the student cannot change their variant
        sc = client_for(self.s1.user)
        self.assertEqual(sc.patch(f"{API}/assignments/{assignment['id']}/", {"variant": v1["id"]}).status_code, 403)

    def test_exam_is_locked_after_first_attempt(self):
        exam, v = self.build_exam()
        self.assign_group(exam)
        self.sit(self.s1, correct=2)
        self.assertEqual(self.tc.put(f"{API}/variants/{v['id']}/questions/", {"question_ids": []}).json()["code"], "exam_has_attempts")
        self.assertEqual(self.tc.delete(f"{API}/examinations/{exam['id']}/").status_code, 409)
        qid = self.tc.get(f"{API}/variants/{v['id']}/").json()["questions"][0]["question"]
        r = self.tc.patch(f"{API}/questions/{qid}/", {"options": [{"text": "x", "is_correct": True}, {"text": "y"}]}, format="json")
        self.assertEqual(r.json()["code"], "question_in_use")

    def test_question_validation(self):
        base = {"text": "t", "section": "GRAMMAR", "level": self.L["B2"].id, "points": 1}
        bad = self.tc.post(f"{API}/questions/", {**base, "question_type": "MCQ",
                           "options": [{"text": "a", "is_correct": True}, {"text": "b", "is_correct": True}]})
        self.assertEqual(bad.status_code, 400)
        listening = self.tc.post(f"{API}/questions/", {**base, "question_type": "LISTENING",
                                "options": [{"text": "a", "is_correct": True}, {"text": "b"}]})
        self.assertEqual(listening.status_code, 400)
        ok = self.tc.post(f"{API}/questions/", {**base, "question_type": "FILL", "options": [{"text": "went"}]})
        self.assertEqual(ok.status_code, 201, ok.content)
        self.assertTrue(ok.json()["options"][0]["is_correct"])


class SharedExamTests(TestCase):
    def setUp(self):
        self.L = make_levels()
        self.admin = make_user("admin", Role.ADMIN)
        self.teacher = make_user("teach", Role.TEACHER)
        self.other = make_user("teach2", Role.TEACHER)
        self.group = Group.objects.create(name="G", level=self.L["A1"], teacher=self.teacher.teacher_profile)
        self.placed = make_student("placed", self.L["A1"])
        self.unplaced = make_student("unplaced", None)          # registered as A1, placement not taken yet
        self.unplaced.initial_level = self.L["A1"]
        self.unplaced.save()
        self.wrong = make_student("wrong", self.L["B1"])
        for s in (self.placed, self.unplaced, self.wrong):
            StudentGroup.objects.create(student=s, group=self.group)
        from apps.core.tests.helpers import make_exam
        self.exam, _ = make_exam(self.L["A1"], kind="UPGRADE", target=self.L["A2"], creator=self.admin, high=None)
        self.ac, self.tc = client_for(self.admin), client_for(self.teacher)

    def test_admin_gives_an_exam_to_a_teacher(self):
        self.assertEqual(self.tc.get(f"{API}/examinations/").json()["count"], 0)       # created by the admin: invisible
        r = self.ac.patch(f"{API}/examinations/{self.exam.id}/", {"teachers": [self.teacher.id]}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["teacher_names"], [self.teacher.full_name])
        self.assertEqual(self.tc.get(f"{API}/examinations/").json()["count"], 1)
        self.assertEqual(client_for(self.other).get(f"{API}/examinations/").json()["count"], 0)
        # a teacher cannot hand exams out
        self.assertEqual(self.tc.patch(f"{API}/examinations/{self.exam.id}/", {"teachers": [self.other.id]}, format="json").status_code, 400)
        self.assertEqual(self.tc.get(f"{API}/analytics/dashboard/").json()["totals"]["examinations"], 1)

    def test_teacher_assigns_the_shared_exam_and_gets_a_clear_report(self):
        self.ac.patch(f"{API}/examinations/{self.exam.id}/", {"teachers": [self.teacher.id]}, format="json")
        r = self.tc.post(f"{API}/examinations/{self.exam.id}/assign/", {"group_ids": [self.group.id]}).json()
        self.assertEqual(r["created"], 2)                      # placed + not-yet-placed (estimated level A1)
        self.assertEqual(r["skipped_level_mismatch"], [{"name": self.wrong.user.full_name, "level": "B1"}])
        # results of the shared exam reach the teacher
        self.assertEqual(self.tc.get(f"{API}/assignments/?examination={self.exam.id}").json()["count"], 2)


class TeacherOwnStudentsTests(TestCase):
    def setUp(self):
        self.L = make_levels()
        self.teacher = make_user("teach", Role.TEACHER)
        self.other = make_user("teach2", Role.TEACHER)
        self.mine = Group.objects.create(name="Mine", level=self.L["A1"], teacher=self.teacher.teacher_profile)
        self.theirs = Group.objects.create(name="Theirs", level=self.L["A1"], teacher=self.other.teacher_profile)
        self.free = make_student("free", self.L["A1"])                    # in no group
        self.taken = make_student("taken", self.L["A1"])
        StudentGroup.objects.create(student=self.taken, group=self.theirs)
        self.tc = client_for(self.teacher)

    def test_teacher_finds_and_adds_students_without_a_group(self):
        found = self.tc.get(f"{API}/students/?available=1").json()["results"]
        self.assertEqual([s["id"] for s in found], [self.free.id])        # not the other teacher's student
        r = self.tc.post(f"{API}/groups/{self.mine.id}/members/", {"student_id": self.free.id})
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(self.tc.get(f"{API}/students/").json()["count"], 1)   # now one of "my students"
        self.assertEqual(self.tc.get(f"{API}/students/?available=1").json()["count"], 0)
        # cannot take someone else's student, nor touch someone else's group
        self.assertEqual(self.tc.post(f"{API}/groups/{self.mine.id}/members/", {"student_id": self.taken.id}).status_code, 403)
        self.assertEqual(self.tc.post(f"{API}/groups/{self.theirs.id}/members/", {"student_id": self.free.id}).status_code, 404)
        # removing from the own group works
        self.assertEqual(self.tc.delete(f"{API}/groups/{self.mine.id}/members/", {"student_id": self.free.id}).status_code, 204)

    def test_teacher_registers_a_new_student_into_own_group_only(self):
        body = {"first_name": "Ali", "last_name": "Vali", "phone": "998901110000", "initial_level": self.L["A1"].id}
        self.assertEqual(self.tc.post(f"{API}/students/", body).status_code, 403)                          # a group is required
        self.assertEqual(self.tc.post(f"{API}/students/", {**body, "group": self.theirs.id}).status_code, 403)
        r = self.tc.post(f"{API}/students/", {**body, "group": self.mine.id})
        self.assertEqual(r.status_code, 201, r.content)
        self.assertIn("password", r.json()["credentials"])
        self.assertEqual(self.tc.get(f"{API}/students/").json()["count"], 1)
        # students cannot do any of this
        stu = make_user("stu", Role.STUDENT)
        self.assertEqual(client_for(stu).post(f"{API}/students/", {**body, "group": self.mine.id}).status_code, 403)


class TeacherSeesStudentLoginTests(TestCase):
    def test_teacher_gets_login_and_a_fresh_password_for_own_students_only(self):
        L = make_levels()
        teacher, other = make_user("teach", Role.TEACHER), make_user("teach2", Role.TEACHER)
        mine = Group.objects.create(name="Mine", level=L["A1"], teacher=teacher.teacher_profile)
        student = make_student("stu", L["A1"])
        StudentGroup.objects.create(student=student, group=mine)
        tc = client_for(teacher)
        row = tc.get(f"{API}/students/").json()["results"][0]
        self.assertEqual(row["username"], "stu")                                    # the login is always visible
        r = tc.post(f"{API}/students/{student.id}/reset-password/")
        self.assertEqual(r.status_code, 200, r.content)
        creds = r.json()
        self.assertEqual(creds["username"], "stu")
        from rest_framework.test import APIClient
        self.assertEqual(APIClient().post(f"{API}/auth/login/", {"username": "stu", "password": creds["password"]}).status_code, 200)
        self.assertEqual(client_for(other).post(f"{API}/students/{student.id}/reset-password/").status_code, 404)
        self.assertEqual(client_for(student.user).post(f"{API}/students/{student.id}/reset-password/").status_code, 403)
