from django.core import mail
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.accounts.verification import check_captcha, make_captcha
from apps.core.tests.helpers import make_levels, make_user, signup

API = "/api/v1"


class SignupTests(TestCase):
    def setUp(self):
        cache.clear()
        make_levels()
        self.c = APIClient()

    def start(self, **over):
        token, _img, answer = make_captcha()
        body = {"first_name": "Ali", "last_name": "Vali", "username": "Ali_Vali", "password": "Zx-91kLm-pass",
                "captcha_token": token, "captcha_answer": answer.lower(), **over}
        return self.c.post(f"{API}/auth/register/", body, format="json")

    def test_captcha_endpoint_gives_a_picture_not_the_answer(self):
        r = self.c.get(f"{API}/auth/captcha/").json()
        self.assertTrue(r["image"].startswith("data:image/png;base64,"))
        self.assertEqual(set(r), {"token", "image"})

    def test_captcha_is_checked_and_single_use(self):
        token, _img, answer = make_captcha()
        self.assertFalse(check_captcha(token, "WRONG"))
        self.assertTrue(check_captcha(token, answer))
        self.assertFalse(check_captcha(token, answer))  # replay
        r = self.start(captcha_answer="nope")
        self.assertEqual(r.json()["code"], "captcha_invalid")
        self.assertEqual(self.start(website="http://spam").json()["code"], "captcha_invalid")  # honeypot
        self.assertEqual(User.objects.filter(role=Role.STUDENT).count(), 0)

    def test_account_created_with_login_and_signed_in(self):
        r = self.start()
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(r.json()["access"])
        self.assertEqual(len(mail.outbox), 0)
        user = User.objects.get(username="ali_vali")
        self.assertEqual((user.role, user.first_name, user.email), (Role.STUDENT, "Ali", ""))
        self.assertEqual(APIClient().post(f"{API}/auth/login/", {"username": "ali_vali", "password": "Zx-91kLm-pass"}, format="json").status_code, 200)

    def test_login_taken_invalid_and_bad_password(self):
        make_user("ali_vali", Role.STUDENT)
        self.assertEqual(self.start().json()["errors"]["username"], ["username_taken"])
        self.assertEqual(self.start(username="ali vali!").json()["errors"]["username"], ["username_invalid"])
        self.assertIn("password", self.start(username="new_one", password="123").json()["errors"])

    def test_helper_signup_works(self):
        self.assertEqual(signup(self.c, username="xurshid").status_code, 201)
