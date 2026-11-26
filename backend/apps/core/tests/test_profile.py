from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import Role
from apps.core.tests.helpers import PASSWORD, client_for, make_levels, make_student, make_user

API = "/api/v1"


class SelfServiceAccountTests(TestCase):
    def setUp(self):
        make_levels()
        self.student = make_student("998901112233")
        self.c = client_for(self.student.user)

    def login(self, username, password):
        return APIClient().post(f"{API}/auth/login/", {"username": username, "password": password}, format="json").status_code

    def test_student_changes_login_and_password(self):
        r = self.c.post(f"{API}/auth/change-username/", {"username": "ali_valiyev", "password": PASSWORD}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["username"], "ali_valiyev")
        r = self.c.post(f"{API}/auth/change-password/", {"old_password": PASSWORD, "new_password": "Yangi-Parol-2026"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(self.login("ali_valiyev", "Yangi-Parol-2026"), 200)
        self.assertEqual(self.login("998901112233", PASSWORD), 401)

    def test_rules(self):
        make_user("taken", Role.STUDENT)
        bad = [({"username": "taken", "password": PASSWORD}, "username"),        # someone else's login
               ({"username": "TAKEN", "password": PASSWORD}, "username"),        # case does not matter
               ({"username": "ali valiyev", "password": PASSWORD}, "username"),  # no spaces
               ({"username": "ab", "password": PASSWORD}, "username"),           # too short
               ({"username": "new_login", "password": "wrong"}, "password")]     # current password required
        for body, field in bad:
            r = self.c.post(f"{API}/auth/change-username/", body, format="json")
            self.assertEqual(r.status_code, 400, body)
            self.assertIn(field, r.json()["errors"], r.json())
        self.student.user.refresh_from_db()
        self.assertEqual(self.student.user.username, "998901112233")

    def test_needs_login(self):
        self.assertEqual(APIClient().post(f"{API}/auth/change-username/", {"username": "x_y_z", "password": "p"}, format="json").status_code, 401)
