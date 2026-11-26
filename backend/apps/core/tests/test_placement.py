from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Role
from apps.core.tests.helpers import answer_all, client_for, make_exam, make_levels, make_user
from apps.examinations.models import ExamAttempt, ExamAssignment
from apps.examinations.services import sweep_expired_attempts
from apps.results.models import ExamResult, OfferStatus, Recommendation
from apps.students.models import LevelChangeHistory, StudentProfile


class PlacementFlowTests(TestCase):
    def setUp(self):
        self.levels = make_levels()
        self.admin = make_user("admin", Role.ADMIN)
        self.recep = make_user("recep", Role.RECEPTIONIST)
        self.exams = {c: make_exam(l, creator=self.admin)[0] for c, l in self.levels.items()}
        self.rc = client_for(self.recep)

    def register(self, level="B1"):
        # the front desk no longer registers students; the admin (or the student) does, reception runs the test
        body = {"first_name": "Ali", "last_name": "Valiyev", "phone": "998901112233", "initial_level": self.levels[level].id}
        self.assertEqual(self.rc.post("/api/v1/students/", body).status_code, 403)
        r = client_for(self.admin).post("/api/v1/students/", {
            "first_name": "Ali", "last_name": "Valiyev", "phone": "998901112233",
            "initial_level": self.levels[level].id})
        self.assertEqual(r.status_code, 201, r.content)
        self.assertIn("password", r.json()["credentials"])
        return r.json()["id"]

    def assign_and_start(self, student_id, level):
        r = self.rc.post("/api/v1/placements/", {"student": student_id, "level": self.levels[level].id})
        self.assertEqual(r.status_code, 201, r.content)
        s = self.rc.post(f"/api/v1/placements/{r.json()['id']}/start/")
        self.assertEqual(s.status_code, 200, s.content)
        return r.json()["id"], s.json()

    def kiosk(self, token):
        from rest_framework.test import APIClient
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        return c

    def take(self, kc, attempt_id, correct):
        answer_all(kc, attempt_id, correct_count=correct)
        r = kc.post(f"/api/v1/attempts/{attempt_id}/submit/")
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()["result_id"]

    def test_duplicate_placement_assignment_is_rejected(self):
        sid = self.register()
        self.rc.post("/api/v1/placements/", {"student": sid, "level": self.levels["B1"].id})
        r = self.rc.post("/api/v1/placements/", {"student": sid, "level": self.levels["B1"].id})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["code"], "placement_already_assigned")

    def test_low_score_offers_previous_level_and_chain_completes(self):
        sid = self.register("B1")
        aid, start = self.assign_and_start(sid, "B1")
        kc = self.kiosk(start["kiosk_token"])
        rid = self.take(kc, start["attempt_id"], correct=1)  # 25 % < 50 %
        res = ExamResult.objects.get(pk=rid)
        self.assertEqual(res.recommendation, Recommendation.LOWER)
        self.assertEqual(res.recommended_level.code, "A2")
        self.assertEqual(res.offer_status, OfferStatus.PENDING)
        self.assertIsNone(StudentProfile.objects.get(pk=sid).current_level)  # not decided yet

        r = kc.post(f"/api/v1/results/{rid}/offer/", {"accept": True})
        self.assertEqual(r.status_code, 200, r.content)
        new_assignment = r.json()["assignment_id"]
        self.assertEqual(ExamAssignment.objects.get(pk=new_assignment).examination.level.code, "A2")
        # the offer can only be answered once
        self.assertEqual(kc.post(f"/api/v1/results/{rid}/offer/", {"accept": False}).status_code, 409)

        a2 = kc.post(f"/api/v1/assignments/{new_assignment}/start/").json()
        self.take(kc, a2["id"], correct=3)  # 75 % -> confirm A2
        self.assertEqual(StudentProfile.objects.get(pk=sid).current_level.code, "A2")
        hist = LevelChangeHistory.objects.get(student_id=sid)
        self.assertEqual((hist.from_level, hist.to_level.code, hist.reason), (None, "A2", "PLACEMENT"))

    def test_high_score_offers_next_level_and_decline_keeps_tested_level(self):
        sid = self.register("B1")
        _, start = self.assign_and_start(sid, "B1")
        kc = self.kiosk(start["kiosk_token"])
        rid = self.take(kc, start["attempt_id"], correct=4)  # 100 %
        res = ExamResult.objects.get(pk=rid)
        self.assertEqual((res.recommendation, res.recommended_level.code), (Recommendation.HIGHER, "B2"))
        r = kc.post(f"/api/v1/results/{rid}/offer/", {"accept": False})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(StudentProfile.objects.get(pk=sid).current_level.code, "B1")

    def test_acceptable_score_confirms_level_immediately(self):
        sid = self.register("B1")
        _, start = self.assign_and_start(sid, "B1")
        kc = self.kiosk(start["kiosk_token"])
        rid = self.take(kc, start["attempt_id"], correct=3)  # 75 %
        res = ExamResult.objects.get(pk=rid)
        self.assertEqual((res.recommendation, res.offer_status), (Recommendation.CONFIRM, OfferStatus.NONE))
        self.assertEqual(StudentProfile.objects.get(pk=sid).current_level.code, "B1")

    def test_cannot_be_offered_a_level_already_attempted(self):
        sid = self.register("A2")
        _, start = self.assign_and_start(sid, "A2")
        kc = self.kiosk(start["kiosk_token"])
        rid = self.take(kc, start["attempt_id"], correct=4)  # high -> offer B1
        a = kc.post(f"/api/v1/results/{rid}/offer/", {"accept": True}).json()["assignment_id"]
        b1 = kc.post(f"/api/v1/assignments/{a}/start/").json()
        rid2 = self.take(kc, b1["id"], correct=0)  # low -> A2 already taken => no offer
        res = ExamResult.objects.get(pk=rid2)
        self.assertEqual(res.offer_status, OfferStatus.NONE)
        self.assertEqual(StudentProfile.objects.get(pk=sid).current_level.code, "A2")

    def test_refresh_resumes_same_attempt_and_finished_exam_cannot_restart(self):
        sid = self.register()
        aid, start = self.assign_and_start(sid, "B1")
        kc = self.kiosk(start["kiosk_token"])
        again = kc.post(f"/api/v1/assignments/{aid}/start/").json()
        self.assertEqual(again["id"], start["attempt_id"])
        self.assertEqual(ExamAttempt.objects.count(), 1)
        self.assertLessEqual(again["remaining_seconds"], 30 * 60)
        self.take(kc, start["attempt_id"], correct=3)
        r = kc.post(f"/api/v1/assignments/{aid}/start/")
        self.assertEqual((r.status_code, r.json()["code"]), (409, "attempt_already_finished"))
        self.assertEqual(ExamAttempt.objects.count(), 1)
        # no autosave after submission either
        late = kc.put(f"/api/v1/attempts/{start['attempt_id']}/answers/",
                      {"answers": [{"question_id": 1, "answer": {"option_ids": [1]}}]})
        self.assertEqual(late.status_code, 409)

    def test_payload_never_leaks_correct_answers(self):
        sid = self.register()
        _, start = self.assign_and_start(sid, "B1")
        kc = self.kiosk(start["kiosk_token"])
        body = kc.get(f"/api/v1/attempts/{start['attempt_id']}/").content.decode()
        self.assertNotIn("is_correct", body)
        self.assertNotIn("explanation", body)

    def test_time_expiry_auto_submits_with_saved_answers(self):
        sid = self.register()
        _, start = self.assign_and_start(sid, "B1")
        kc = self.kiosk(start["kiosk_token"])
        answer_all(kc, start["attempt_id"], correct_count=2)
        ExamAttempt.objects.update(deadline_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(sweep_expired_attempts(), 1)
        attempt = ExamAttempt.objects.get()
        self.assertEqual(attempt.status, "AUTO_SUBMITTED")
        self.assertEqual(attempt.result.correct_count, 2)
        self.assertEqual(float(attempt.result.percentage), 50.0)

    def test_expired_attempt_is_finalised_lazily_on_access(self):
        sid = self.register()
        _, start = self.assign_and_start(sid, "B1")
        kc = self.kiosk(start["kiosk_token"])
        ExamAttempt.objects.update(deadline_at=timezone.now() - timedelta(minutes=1))
        data = kc.get(f"/api/v1/attempts/{start['attempt_id']}/").json()
        self.assertEqual(data["status"], "AUTO_SUBMITTED")
        self.assertIsNotNone(data["result_id"])

    def test_kiosk_token_cannot_reach_other_endpoints(self):
        sid = self.register()
        _, start = self.assign_and_start(sid, "B1")
        kc = self.kiosk(start["kiosk_token"])
        for url in ("/api/v1/results/", "/api/v1/auth/me/", "/api/v1/students/"):
            self.assertEqual(kc.get(url).status_code, 403, url)

    def test_section_breakdown_and_totals(self):
        sid = self.register()
        _, start = self.assign_and_start(sid, "B1")
        kc = self.kiosk(start["kiosk_token"])
        rid = self.take(kc, start["attempt_id"], correct=3)
        res = ExamResult.objects.get(pk=rid)
        self.assertEqual((float(res.total_score), float(res.max_score), float(res.percentage)), (3.0, 4.0, 75.0))
        self.assertEqual(res.section_scores["GRAMMAR"]["correct"], 3)
        self.assertEqual((res.correct_count, res.incorrect_count, res.unanswered_count), (3, 1, 0))
