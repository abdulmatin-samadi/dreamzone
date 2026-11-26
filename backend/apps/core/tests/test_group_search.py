from django.test import TestCase

from apps.accounts.models import Role
from apps.academics.models import Group
from apps.core.tests.helpers import client_for, make_levels, make_user

API = "/api/v1"


class GroupSearchTests(TestCase):
    def setUp(self):
        L = make_levels()
        self.t1, self.t2 = make_user("anvar", Role.TEACHER), make_user("bobur", Role.TEACHER)
        self.reception = make_user("reception", Role.RECEPTIONIST)
        Group.objects.create(name="Morning A", level=L["A1"], teacher=self.t1.teacher_profile, schedule="Du-Chor-Ju 09:00-10:30")
        Group.objects.create(name="Evening B", level=L["B1"], teacher=self.t2.teacher_profile, schedule="Se-Pay-Shan 18:00-19:30")
        self.c = client_for(self.reception)

    def names(self, q):
        r = self.c.get(f"{API}/groups/", {"search": q}).json()
        return sorted(g["name"] for g in r["results"])

    def test_receptionist_finds_groups_by_time_teacher_and_level(self):
        self.assertEqual(self.names("18:00"), ["Evening B"])
        self.assertEqual(self.names("Anvar"), ["Morning A"])
        self.assertEqual(self.names("B1"), ["Evening B"])
        self.assertEqual(self.names("a1 09:00"), ["Morning A"])
        self.assertEqual(self.names(""), ["Evening B", "Morning A"])
        self.assertEqual(self.names("nothing"), [])

    def test_receptionist_cannot_edit_groups(self):
        g = Group.objects.first()
        self.assertEqual(self.c.patch(f"{API}/groups/{g.id}/", {"schedule": "x"}, format="json").status_code, 403)
