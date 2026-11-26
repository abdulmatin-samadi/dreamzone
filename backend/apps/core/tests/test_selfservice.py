from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import Role
from apps.academics.models import Group
from apps.core.tests.helpers import answer_all, client_for, make_exam, make_levels, make_user, signup
from apps.students.models import StudentProfile

API = "/api/v1"


class SelfServiceFlowTests(TestCase):
    def setUp(self):
        self.L = make_levels()
        self.admin = make_user("admin", Role.ADMIN)
        self.recep = make_user("recep", Role.RECEPTIONIST)
        for code in ("A2", "B1"):
            make_exam(self.L[code], creator=self.admin)

    def test_student_registers_takes_test_then_reception_adds_to_group(self):
        anon = APIClient()
        r = signup(anon, username="ali", initial_level=self.L["B1"].id)
        self.assertEqual(r.status_code, 201, r.content)
        body = r.json()
        self.assertEqual(body["username"], "ali")

        # logs in with e-mail + password: no test yet - nothing is assigned automatically
        c = APIClient()
        self.assertEqual(c.post(f"{API}/auth/login/", {"username": "ali", "password": "Zx-91kLm-pass"}).status_code, 200)
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION=f"Bearer {body['access']}")
        mine = c.get(f"{API}/my/assignments/").json()
        self.assertEqual(len(mine["results"] if isinstance(mine, dict) else mine), 0)
        # reception gives the placement test
        student = StudentProfile.objects.get(user__username="ali")
        r = client_for(self.recep).post(f"{API}/placements/", {"student": student.id, "level": self.L["B1"].id})
        self.assertEqual(r.status_code, 201, r.content)
        a = c.get(f"{API}/my/assignments/").json()[0]
        attempt = c.post(f"{API}/assignments/{a['id']}/start/").json()
        answer_all(c, attempt["id"], correct_count=3)  # 75 % -> level confirmed
        c.post(f"{API}/attempts/{attempt['id']}/submit/")
        student.refresh_from_db()
        self.assertEqual(student.current_level.code, "B1")

        # reception sees the placed-but-ungrouped student and adds them to a B1 group
        rc = client_for(self.recep)
        self.assertEqual(rc.get(f"{API}/students/?ungrouped=1").json()["count"], 1)
        group = Group.objects.create(name="B1 morning", level=self.L["B1"])
        self.assertEqual(rc.post(f"{API}/groups/{group.id}/members/", {"student_id": student.id}).status_code, 403)  # not the front desk
        self.assertEqual(client_for(self.admin).post(f"{API}/groups/{group.id}/members/", {"student_id": student.id}).status_code, 201)
        self.assertEqual(rc.get(f"{API}/students/?ungrouped=1").json()["count"], 0)
        self.assertEqual(rc.get(f"{API}/analytics/dashboard/").json()["totals"]["awaiting_group"], 0)

    def test_registration_validates_password_level_optional(self):
        anon = APIClient()
        r = signup(anon, username="aziz", password="123")
        self.assertEqual(r.status_code, 400)
        # no level on the form any more: that is fine
        r = signup(anon, username="aziz")
        self.assertEqual(r.status_code, 201, r.content)


class RegisterWithoutLevelTests(TestCase):
    """Self-registration gives no test: a student who is in no group must not see an exam."""

    def setUp(self):
        self.L = make_levels()
        admin = make_user("admin", Role.ADMIN)
        for code in ("A2", "B1"):
            make_exam(self.L[code], creator=admin)

    def test_register_gets_no_test_automatically(self):
        r = signup(APIClient(), username="vali")
        self.assertEqual(r.status_code, 201, r.content)
        mine = APIClient(HTTP_AUTHORIZATION=f"Bearer {r.json()['access']}").get(f"{API}/my/assignments/").json()
        rows = mine["results"] if isinstance(mine, dict) else mine
        self.assertEqual(rows, [])


class WalkInGuestTests(TestCase):
    def setUp(self):
        self.L = make_levels()
        self.admin = make_user("admin", Role.ADMIN)
        self.recep = make_user("recep", Role.RECEPTIONIST)
        make_exam(self.L["B1"], creator=self.admin)
        self.rc = client_for(self.recep)

    def test_reception_runs_test_without_registering_anyone(self):
        r = self.rc.post(f"{API}/placements/quick/", {"level": self.L["B1"].id})
        self.assertEqual(r.status_code, 200, r.content)
        kc = APIClient()
        kc.credentials(HTTP_AUTHORIZATION=f"Bearer {r.json()['kiosk_token']}")
        answer_all(kc, r.json()["attempt_id"], correct_count=3)
        rid = kc.post(f"{API}/attempts/{r.json()['attempt_id']}/submit/").json()["result_id"]
        self.assertEqual(self.rc.get(f"{API}/results/{rid}/").json()["placed_level_code"], "B1")
        # nobody shows up in the students list or the student counters
        self.assertEqual(self.rc.get(f"{API}/students/").json()["count"], 0)
        self.assertEqual(client_for(self.admin).get(f"{API}/analytics/dashboard/").json()["totals"]["students"], 0)
        guest = StudentProfile.objects.get()
        self.assertTrue(guest.is_guest)
        self.assertFalse(guest.user.has_usable_password())

    def test_guest_can_be_enrolled_later(self):
        r = self.rc.post(f"{API}/placements/quick/", {"level": self.L["B1"].id, "first_name": "Ali"})
        guest = StudentProfile.objects.get()
        self.assertEqual(self.rc.post(f"{API}/students/{guest.id}/enroll/", {"first_name": "Ali", "last_name": "Vali", "phone": "998907776655"}).status_code, 403)
        ac = client_for(self.admin)
        e = ac.post(f"{API}/students/{guest.id}/enroll/", {"first_name": "Ali", "last_name": "Vali", "phone": "998907776655"})
        self.assertEqual(e.status_code, 200, e.content)
        self.assertEqual(APIClient().post(f"{API}/auth/login/", {"username": e.json()["username"], "password": e.json()["password"]}).status_code, 200)
        self.assertEqual(self.rc.get(f"{API}/students/").json()["count"], 1)
        self.assertEqual(ac.post(f"{API}/students/{guest.id}/enroll/", {}).status_code, 400)
