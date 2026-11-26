from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Role
from apps.academics.models import Group
from apps.core.tests.helpers import answer_all, client_for, make_exam, make_levels, make_student, make_user
from apps.examinations.models import AttemptStatus, ExamAttempt, ViolationKind
from apps.examinations.services import create_assignments, report_fullscreen, start_attempt, sweep_expired_attempts, terminate_attempt
from apps.students.models import StudentGroup

API = "/api/v1"


class FullscreenEnforcementTests(TestCase):
    def setUp(self):
        self.L = make_levels()
        self.admin = make_user("admin", Role.ADMIN)
        self.teacher = make_user("teach", Role.TEACHER)
        self.other = make_user("teach2", Role.TEACHER)
        self.student = make_student("stu", self.L["A1"])
        group = Group.objects.create(name="G", level=self.L["A1"], teacher=self.teacher.teacher_profile)
        StudentGroup.objects.create(student=self.student, group=group)
        exam, _ = make_exam(self.L["A1"], kind="UPGRADE", target=self.L["A2"], creator=self.teacher, n=4)
        create_assignments(examination=exam, students=[self.student], assigned_by=self.admin)
        self.attempt = start_attempt(assignment_id=self.student.assignments.get().id, student=self.student, started_by=self.student.user)
        self.c = client_for(self.student.user)
        self.url = f"{API}/attempts/{self.attempt.id}/fullscreen/"

    def reload(self):
        return ExamAttempt.objects.get(pk=self.attempt.pk)

    def leave(self, seconds_ago=0):
        r = self.c.post(self.url, {"ok": False, "reason": "fullscreen"}, format="json")
        if seconds_ago:
            ExamAttempt.objects.filter(pk=self.attempt.pk).update(
                violation_deadline_at=timezone.now() + timedelta(seconds=10 - seconds_ago))
        return r

    def test_leave_starts_a_server_side_countdown(self):
        r = self.leave().json()
        self.assertEqual(r["status"], "IN_PROGRESS")
        self.assertTrue(0 < r["violation_seconds_left"] <= 10)
        self.assertIsNotNone(self.reload().violation_deadline_at)
        self.assertTrue(self.attempt.violations.filter(kind=ViolationKind.FULLSCREEN_EXIT).exists())

    def test_returning_in_time_clears_the_violation(self):
        self.leave(seconds_ago=4)
        r = self.c.post(self.url, {"ok": True}, format="json").json()
        self.assertEqual(r["status"], "IN_PROGRESS")
        self.assertIsNone(r["violation_seconds_left"])
        self.assertIsNone(self.reload().violation_deadline_at)

    def test_second_leave_does_not_extend_the_deadline(self):
        self.leave()
        first = self.reload().violation_deadline_at
        self.c.post(self.url, {"ok": False}, format="json")
        self.assertEqual(self.reload().violation_deadline_at, first)

    def test_late_return_is_rejected_by_the_server(self):
        """A modified client that claims 'ok' after 10 s does not escape the termination."""
        answer_all(self.c, self.attempt.id, correct_count=2)
        self.leave()
        ExamAttempt.objects.filter(pk=self.attempt.pk).update(violation_deadline_at=timezone.now() - timedelta(seconds=5))
        r = self.c.post(self.url, {"ok": True}, format="json").json()
        self.assertEqual(r["status"], AttemptStatus.PENDING_TEACHER_APPROVAL)
        a = self.reload()
        self.assertEqual(a.answers.count(), 4)  # answers kept
        self.assertTrue(a.violations.filter(kind=ViolationKind.TERMINATED).exists())
        self.assertFalse(hasattr(a, "result"))

    def test_sweeper_terminates_when_the_client_never_comes_back(self):
        self.leave()
        ExamAttempt.objects.filter(pk=self.attempt.pk).update(violation_deadline_at=timezone.now() - timedelta(seconds=5))
        sweep_expired_attempts()
        self.assertEqual(self.reload().status, AttemptStatus.PENDING_TEACHER_APPROVAL)

    def test_pending_attempt_cannot_be_continued_by_the_student(self):
        self.leave()
        ExamAttempt.objects.filter(pk=self.attempt.pk).update(violation_deadline_at=timezone.now() - timedelta(seconds=5))
        self.c.post(self.url, {"ok": True}, format="json")
        for r in (
            self.c.put(f"{API}/attempts/{self.attempt.id}/answers/", {"answers": [{"question_id": 1, "answer": {}}]}, format="json"),
            self.c.post(f"{API}/attempts/{self.attempt.id}/submit/", {}, format="json"),
            self.c.post(f"{API}/assignments/{self.attempt.assignment_id}/start/"),
        ):
            self.assertEqual(r.status_code, 409)
            self.assertEqual(r.json()["code"], "attempt_pending_approval")
        self.assertEqual(self.c.get(f"{API}/attempts/{self.attempt.id}/").json()["questions"], [])
        st = self.c.get(f"{API}/my/assignments/").json()
        rows = st["results"] if isinstance(st, dict) else st
        self.assertEqual(rows[0]["state"], "pending_approval")

    def stop(self):
        answer_all(self.c, self.attempt.id, correct_count=3)
        self.leave()
        ExamAttempt.objects.filter(pk=self.attempt.pk).update(violation_deadline_at=timezone.now() - timedelta(seconds=5))
        self.c.post(self.url, {"ok": True}, format="json")

    def test_teacher_sees_and_resumes_with_the_remaining_time(self):
        self.stop()
        t = client_for(self.teacher)
        rows = t.get(f"{API}/stopped-attempts/").json()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["answered"], 4)
        self.assertEqual(t.post(f"{API}/stopped-attempts/{self.attempt.id}/resume/").status_code, 200)
        a = self.reload()
        self.assertEqual(a.status, AttemptStatus.IN_PROGRESS)
        self.assertEqual(a.resume_count, 1)
        self.assertGreater(a.deadline_at, timezone.now())
        self.assertEqual(self.c.get(f"{API}/attempts/{self.attempt.id}/").json()["status"], "IN_PROGRESS")

    def test_teacher_finalizes_with_saved_answers(self):
        self.stop()
        r = client_for(self.teacher).post(f"{API}/stopped-attempts/{self.attempt.id}/finalize/")
        self.assertEqual(r.status_code, 200)
        a = self.reload()
        self.assertEqual(a.status, AttemptStatus.SUBMITTED)
        self.assertEqual(float(a.result.percentage), 75.0)

    def test_permissions(self):
        self.stop()
        self.assertEqual(client_for(self.student.user).get(f"{API}/stopped-attempts/").status_code, 403)
        self.assertEqual(client_for(self.student.user).post(f"{API}/stopped-attempts/{self.attempt.id}/resume/").status_code, 403)
        # a teacher who owns neither the exam nor the student cannot touch it
        self.assertEqual(client_for(self.other).get(f"{API}/stopped-attempts/").json(), [])
        self.assertEqual(client_for(self.other).post(f"{API}/stopped-attempts/{self.attempt.id}/resume/").status_code, 404)
        # another student cannot report on this attempt
        other = make_student("stu2", self.L["A1"])
        r = client_for(other.user).post(self.url, {"ok": False}, format="json")
        self.assertEqual(r.status_code, 404)


class StoppedGuestRoutingTests(TestCase):
    """A walk-in guest stopped at the front desk is handled by the receptionist, not by the admin."""

    def setUp(self):
        from apps.students.services import create_guest
        self.L = make_levels()
        self.admin = make_user("admin", Role.ADMIN)
        self.rec = make_user("rec", Role.RECEPTIONIST)
        self.teacher = make_user("teach", Role.TEACHER)
        placement, _ = make_exam(self.L["A1"], creator=self.admin, n=2)
        self.guest = create_guest(initial_level=self.L["A1"], registered_by=self.rec)
        create_assignments(examination=placement, students=[self.guest], assigned_by=self.rec)
        self.g_attempt = start_attempt(assignment_id=self.guest.assignments.get().id, student=self.guest, started_by=self.rec)
        # a registered student's upgrade test stopped as well
        self.student = make_student("stu", self.L["A1"])
        upgrade, _ = make_exam(self.L["A1"], kind="UPGRADE", target=self.L["A2"], creator=self.teacher, n=2)
        create_assignments(examination=upgrade, students=[self.student], assigned_by=self.admin)
        self.u_attempt = start_attempt(assignment_id=self.student.assignments.get().id, student=self.student, started_by=self.student.user)
        for a in (self.g_attempt, self.u_attempt):
            report_fullscreen(a.id, ok=False)
            ExamAttempt.objects.filter(pk=a.pk).update(violation_deadline_at=timezone.now() - timedelta(seconds=5))
            terminate_attempt(a.id)

    def ids(self, user):
        return {r["id"] for r in client_for(user).get(f"{API}/stopped-attempts/").json()}

    def test_routing(self):
        self.assertEqual(self.ids(self.rec), {self.g_attempt.id})      # guest -> reception only
        self.assertEqual(self.ids(self.admin), {self.u_attempt.id})    # admin no longer gets the guest
        self.assertEqual(self.ids(self.teacher), {self.u_attempt.id})
        row = client_for(self.rec).get(f"{API}/stopped-attempts/").json()[0]
        self.assertTrue(row["is_guest"]); self.assertEqual(row["assignment_id"], self.g_attempt.assignment_id)

    def test_reception_resumes_and_restarts_the_kiosk(self):
        c = client_for(self.rec)
        self.assertEqual(c.post(f"{API}/stopped-attempts/{self.g_attempt.id}/resume/").status_code, 200)
        r = c.post(f"{API}/placements/{self.g_attempt.assignment_id}/start/").json()
        self.assertEqual(r["attempt_id"], self.g_attempt.id)        # the same attempt continues, answers kept
        self.assertTrue(r["kiosk_token"])
        # the receptionist cannot touch the registered student's upgrade test
        self.assertEqual(c.post(f"{API}/stopped-attempts/{self.u_attempt.id}/resume/").status_code, 404)
        self.assertEqual(client_for(self.admin).post(f"{API}/stopped-attempts/{self.g_attempt.id}/resume/").status_code, 404)
