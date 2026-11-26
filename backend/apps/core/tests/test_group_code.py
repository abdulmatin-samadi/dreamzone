from django.core.cache import cache
from django.test import TestCase

from apps.accounts.models import Role
from apps.academics.models import CODE_ALPHABET, Group
from apps.core.tests.helpers import client_for, make_levels, make_student, make_user

API = "/api/v1"


class GroupCodeTests(TestCase):
    def setUp(self):
        cache.clear()  # throttle counters
        self.L = make_levels()
        self.admin = make_user("admin", Role.ADMIN)
        self.teacher = make_user("teach", Role.TEACHER)
        self.other = make_user("teach2", Role.TEACHER)
        self.group = Group.objects.create(name="Morning", level=self.L["A1"], teacher=self.teacher.teacher_profile)
        self.student = make_student("ali", self.L["A1"])

    def test_code_is_generated_on_create(self):
        r = client_for(self.admin).post(f"{API}/groups/", {"name": "Evening", "level": self.L["A2"].id}, format="json")
        code = r.json()["join_code"]
        self.assertEqual(len(code), 6)
        self.assertTrue(set(code) <= set(CODE_ALPHABET))
        self.assertNotEqual(code, self.group.join_code)

    def test_student_joins_with_the_code(self):
        c = client_for(self.student.user)
        r = c.post(f"{API}/groups/join/", {"code": f"  {self.group.join_code.lower()} "}, format="json")  # spaces / case ignored
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["name"], "Morning")
        self.assertNotIn("join_code", r.json())
        self.assertTrue(self.student.groups.filter(pk=self.group.pk).exists())
        self.assertEqual(c.post(f"{API}/groups/join/", {"code": self.group.join_code}, format="json").json()["code"], "already_in_group")
        groups = c.get(f"{API}/groups/").json()["results"]
        self.assertEqual([g["name"] for g in groups], ["Morning"])
        self.assertNotIn("join_code", groups[0])
        # the teacher sees the new member
        self.assertEqual(len(client_for(self.teacher).get(f"{API}/groups/{self.group.id}/members/").json()), 1)

    def test_wrong_or_inactive_code(self):
        c = client_for(self.student.user)
        self.assertEqual(c.post(f"{API}/groups/join/", {"code": "ZZZZZZ"}, format="json").json()["code"], "group_code_invalid")
        self.assertEqual(c.post(f"{API}/groups/join/", {"code": ""}, format="json").status_code, 404)
        Group.objects.filter(pk=self.group.pk).update(is_active=False)
        self.assertEqual(c.post(f"{API}/groups/join/", {"code": self.group.join_code}, format="json").status_code, 404)

    def test_regenerate_and_permissions(self):
        old = self.group.join_code
        r = client_for(self.teacher).post(f"{API}/groups/{self.group.id}/regenerate-code/")
        self.assertEqual(r.status_code, 200)
        self.assertNotEqual(r.json()["join_code"], old)
        # the old code stops working
        self.assertEqual(client_for(self.student.user).post(f"{API}/groups/join/", {"code": old}, format="json").status_code, 404)
        self.assertEqual(client_for(self.other).post(f"{API}/groups/{self.group.id}/regenerate-code/").status_code, 404)
        self.assertEqual(client_for(self.student.user).post(f"{API}/groups/{self.group.id}/regenerate-code/").status_code, 403)
        self.assertEqual(client_for(self.teacher).post(f"{API}/groups/join/", {"code": old}, format="json").status_code, 403)

    def test_guessing_is_throttled(self):
        c = client_for(self.student.user)
        codes = [c.post(f"{API}/groups/join/", {"code": f"AAAAA{i}"}, format="json").status_code for i in range(12)]
        self.assertIn(429, codes)

    def test_only_admin_and_teacher_see_the_code(self):
        self.assertEqual(client_for(self.admin).get(f"{API}/groups/").json()["results"][0]["join_code"], self.group.join_code)
        self.assertEqual(client_for(self.teacher).get(f"{API}/groups/").json()["results"][0]["join_code"], self.group.join_code)
        desk = client_for(make_user("desk", Role.RECEPTIONIST))
        self.assertNotIn("join_code", desk.get(f"{API}/groups/").json()["results"][0])
        self.assertNotIn("join_code", desk.get(f"{API}/groups/{self.group.id}/").json())
        self.assertEqual(desk.post(f"{API}/groups/{self.group.id}/regenerate-code/").status_code, 403)
