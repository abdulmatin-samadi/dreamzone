from django.test import TestCase

from apps.accounts.models import Role
from apps.academics.models import Group
from apps.core.tests.helpers import client_for, make_exam, make_levels, make_student, make_user, mcq
from apps.examinations.models import VariantQuestion
from apps.examinations.services import create_assignments, start_attempt
from apps.questions.models import Question, QuestionType, Section
from apps.results.models import ApprovalStatus, ExamResult, OfferStatus
from apps.students.models import StudentGroup, StudentProfile

API = "/api/v1"


class WritingFlowTests(TestCase):
    def setUp(self):
        self.L = make_levels()
        self.admin = make_user("admin", Role.ADMIN)
        self.teacher = make_user("teach", Role.TEACHER)
        self.other = make_user("teach2", Role.TEACHER)
        self.student = make_student("stu", self.L["A1"])
        group = Group.objects.create(name="G", level=self.L["A1"], teacher=self.teacher.teacher_profile)
        StudentGroup.objects.create(student=self.student, group=group)

    def make_writing_exam(self, kind="UPGRADE", **kw):
        exam, variant = make_exam(self.L["A1"], kind=kind, target=self.L["A2"] if kind == "UPGRADE" else None,
                                  creator=self.teacher if kind == "UPGRADE" else self.admin, n=1, passing=5.5, **kw)  # half of 1 + 10 points
        w = Question.objects.create(text="Write an email to a friend.", instruction="Writing task", question_type=QuestionType.WRITING,
                                    section=Section.WRITING, level=self.L["A1"], points=10, created_by=self.admin, category="WRITING")
        VariantQuestion.objects.create(variant=variant, question=w, order=1)
        return exam, w

    def sit(self, exam, correct_first=True, essay="Dear Sam, I had a lovely weekend. We went to the park."):
        create_assignments(examination=exam, students=[self.student], assigned_by=self.admin)
        attempt = start_attempt(assignment_id=self.student.assignments.get().id, student=self.student, started_by=self.student.user)
        c = client_for(self.student.user)
        data = c.get(f"{API}/attempts/{attempt.id}/").json()
        items = []
        for q in data["questions"]:
            if q["type"] == "WRITING":
                items.append({"question_id": q["id"], "answer": {"text": essay}})
            else:
                opt = next(o["id"] for o in q["options"] if o["text"] == ("right" if correct_first else "wrong"))
                items.append({"question_id": q["id"], "answer": {"option_ids": [opt]}})
        self.assertEqual(c.put(f"{API}/attempts/{attempt.id}/answers/", {"answers": items}).status_code, 200)
        rid = c.post(f"{API}/attempts/{attempt.id}/submit/").json()["result_id"]
        return c, ExamResult.objects.get(pk=rid)

    def test_upgrade_waits_for_the_teacher_then_goes_to_approval(self):
        exam, w = self.make_writing_exam()
        c, res = self.sit(exam)
        self.assertTrue(res.writing_pending)
        self.assertEqual(float(res.total_score), 1.0)                       # only the auto-graded part so far
        self.assertEqual(res.approval_status, ApprovalStatus.NOT_REQUIRED)  # no decision before the writing is scored
        mine = c.get(f"{API}/results/{res.id}/").json()  # the student sees no points at all
        self.assertEqual((mine["writing"], mine["total_score"], mine["correct_count"], mine["passed"]), ([], None, None, None))
        self.assertEqual(c.get(f"{API}/results/{res.id}/export/").status_code, 403)
        self.assertEqual(client_for(self.teacher).get(f"{API}/results/{res.id}/").json()["writing"][0]["needs_review"], True)

        tc = client_for(self.teacher)
        url = f"{API}/results/{res.id}/grade-writing/"
        self.assertEqual(tc.post(url, {"grades": [{"question_id": w.id, "points": 11}]}, format="json").status_code, 400)   # > max
        self.assertEqual(client_for(self.other).post(url, {"grades": [{"question_id": w.id, "points": 5}]}, format="json").status_code, 404)
        self.assertEqual(c.post(url, {"grades": [{"question_id": w.id, "points": 10}]}, format="json").status_code, 403)       # student
        r = tc.post(url, {"grades": [{"question_id": w.id, "points": 7, "feedback": "Good, check the tenses."}]}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        res.refresh_from_db()
        self.assertFalse(res.writing_pending)
        self.assertEqual((float(res.total_score), float(res.max_score)), (8.0, 11.0))
        self.assertTrue(res.passed)                                          # 72.7 % >= 50 %
        self.assertEqual(res.approval_status, ApprovalStatus.PENDING)      # now the teacher can approve the level change
        # staff see the score and the feedback (the student does not); a second grading is refused
        self.assertEqual(c.get(f"{API}/results/{res.id}/").json()["writing"], [])
        done = tc.get(f"{API}/results/{res.id}/").json()["writing"][0]
        self.assertEqual((done["points"], done["feedback"], done["needs_review"]), (7.0, "Good, check the tenses.", False))
        # before the decision the score can be corrected, also "out of" another maximum (like speaking)
        self.assertEqual(tc.post(url, {"grades": [{"question_id": w.id, "points": 16, "max": 15}]}, format="json").json()["code"], "points_out_of_range")
        d = tc.post(url, {"grades": [{"question_id": w.id, "points": 12, "max": 15}]}, format="json").json()
        self.assertEqual((float(d["total_score"]), float(d["max_score"]), d["writing"][0]["max_points"]), (13.0, 16.0, 15.0))
        self.assertEqual(d["approval_status"], "PENDING")
        self.assertEqual(tc.post(f"{API}/results/{res.id}/reject/").status_code, 200)
        self.assertEqual(tc.post(url, {"grades": [{"question_id": w.id, "points": 9}]}, format="json").json()["code"], "result_locked")

    def test_placement_decision_waits_for_the_writing_score(self):
        StudentProfile.objects.filter(pk=self.student.pk).update(current_level=None)   # a new student, not placed yet
        exam, w = self.make_writing_exam(kind="PLACEMENT")
        c, res = self.sit(exam)
        self.assertTrue(res.writing_pending)
        self.assertEqual(res.offer_status, OfferStatus.NONE)
        self.assertIsNone(StudentProfile.objects.get(pk=self.student.pk).current_level)       # level not decided yet
        url = f"{API}/results/{res.id}/grade-writing/"
        body = {"grades": [{"question_id": w.id, "points": 9}]}
        # the guest's writing is reception's job (the admin may score it too), not the teacher's
        self.assertEqual(client_for(self.teacher).post(url, body, format="json").json()["code"], "writing_not_yours")
        rc = client_for(make_user("rec", Role.RECEPTIONIST))
        self.assertEqual([x["id"] for x in rc.get(f"{API}/results/writing-queue/").json()], [res.id])
        self.assertEqual(client_for(self.teacher).get(f"{API}/results/writing-queue/").json(), [])
        self.assertEqual(rc.get(f"{API}/analytics/dashboard/").json()["totals"]["writing_pending"], 1)
        r = rc.post(url, body, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(StudentProfile.objects.get(pk=self.student.pk).current_level.code, "A1")   # placed once everything is scored

    def test_blank_writing_needs_no_review_and_counts_as_skipped(self):
        exam, w = self.make_writing_exam()
        c, res = self.sit(exam, essay="   ")
        self.assertFalse(res.writing_pending)
        self.assertEqual(res.unanswered_count, 1)

    def test_pending_filter_and_dashboard(self):
        exam, w = self.make_writing_exam()
        self.sit(exam)
        tc = client_for(self.teacher)
        self.assertEqual(tc.get(f"{API}/results/?writing_pending=true").json()["count"], 1)
        self.assertEqual(tc.get(f"{API}/analytics/dashboard/").json()["totals"]["writing_pending"], 1)
        self.assertEqual(client_for(self.admin).get(f"{API}/analytics/dashboard/").json()["totals"]["writing_pending"], 1)
        # upgrade writing is the teacher's (or the admin's): reception cannot score it
        res = ExamResult.objects.get()
        body = {"grades": [{"question_id": w.id, "points": 5}]}
        self.assertEqual(client_for(make_user("rec2", Role.RECEPTIONIST)).post(f"{API}/results/{res.id}/grade-writing/", body, format="json").status_code in (403, 404), True)
        self.assertEqual(client_for(make_user("rec", Role.RECEPTIONIST)).get(f"{API}/results/writing-queue/").json(), [])

    def test_writing_answer_validation_and_question_creation(self):
        ac = client_for(self.admin)
        r = ac.post(f"{API}/questions/", {"text": "Write about your family.", "question_type": "WRITING", "section": "WRITING",
                                          "level": self.L["A1"].id, "points": 10, "options": []}, format="json")
        self.assertEqual(r.status_code, 201, r.content)


class AdminScoresWritingTests(TestCase):
    """The admin may score written answers too (not only the teacher / reception)."""

    setUp = WritingFlowTests.setUp
    make_writing_exam = WritingFlowTests.make_writing_exam
    sit = WritingFlowTests.sit

    def test_admin_scores_upgrade_writing(self):
        exam, w = self.make_writing_exam()
        _c, res = self.sit(exam)
        r = client_for(self.admin).post(f"{API}/results/{res.id}/grade-writing/", {"grades": [{"question_id": w.id, "points": 6}]}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertFalse(r.json()["writing_pending"])
