from django.test import TestCase

from apps.accounts.models import Role
from apps.academics.models import Group
from apps.core.tests.helpers import answer_all, client_for, make_exam, make_levels, make_student, make_user
from apps.examinations.services import create_assignments, start_attempt, submit_attempt
from apps.students.models import StudentGroup

API = "/api/v1"


class StatsTests(TestCase):
    def setUp(self):
        self.L = make_levels()
        self.admin = make_user("admin", Role.ADMIN)
        self.teacher = make_user("teach", Role.TEACHER)
        self.other = make_user("teach2", Role.TEACHER)
        self.group = Group.objects.create(name="Morning", level=self.L["A1"], teacher=self.teacher.teacher_profile)
        self.s1, self.s2 = make_student("ali", self.L["A1"]), make_student("vali", self.L["A1"])
        self.outsider = make_student("guli", self.L["A1"])
        for s in (self.s1, self.s2):
            StudentGroup.objects.create(student=s, group=self.group)

    def sit(self, student, correct, n=4):
        exam, _ = make_exam(self.L["A1"], kind="UPGRADE", target=self.L["A2"], creator=self.teacher, n=n)
        create_assignments(examination=exam, students=[student], assigned_by=self.admin)
        attempt = start_attempt(assignment_id=student.assignments.get(examination=exam).id, student=student, started_by=student.user)
        answer_all(client_for(student.user), attempt.id, correct_count=correct)
        return submit_attempt(attempt.id)

    def test_student_sees_only_own_progress(self):
        self.sit(self.s1, 2)   # 50 %
        self.sit(self.s1, 4)   # 100 %
        self.sit(self.s2, 1)   # someone else
        d = client_for(self.s1.user).get(f"{API}/analytics/stats/").json()
        self.assertEqual(d["summary"]["results"], 2)
        self.assertEqual((d["summary"]["avg_score"], d["summary"]["avg_max"]), (3.0, 4.0))  # points
        self.assertEqual((d["summary"]["best_score"], d["summary"]["best_max"]), (4.0, 4.0))
        self.assertEqual([(t["score"], t["max"]) for t in d["timeline"]], [(2.0, 4.0), (4.0, 4.0)])
        self.assertEqual([t["passed"] for t in d["timeline"]], [None, None])  # the teacher has not decided yet
        self.assertEqual(d["summary"]["passed"], 0)
        self.assertEqual(d["sections"][0]["section"], "GRAMMAR")
        self.assertEqual((d["sections"][0]["score"], d["sections"][0]["max"]), (6.0, 8.0))
        self.assertEqual(d["level"]["current"], "A1")

    def test_teacher_class_overview(self):
        self.sit(self.s1, 4)   # 100
        self.sit(self.s2, 1)   # 25
        d = client_for(self.teacher).get(f"{API}/analytics/stats/").json()
        self.assertEqual(d["summary"]["results"], 2)
        self.assertEqual(d["summary"]["avg_score"], 2.5)
        g = d["groups"][0]
        self.assertEqual((g["name"], g["students"], g["results"], g["avg_score"], g["avg_max"]), ("Morning", 2, 2, 2.5, 4.0))
        self.assertEqual(d["top_students"][0]["name"], "Ali Test")
        self.assertEqual([s["name"] for s in d["attention"]], ["Vali Test"])
        self.assertEqual(len(d["exams"]), 2)
        self.assertEqual(d["monthly"][-1]["results"], 2)

    def test_scoping(self):
        self.sit(self.s1, 4)
        # a teacher with neither the exam nor the students sees nothing of them
        d = client_for(self.other).get(f"{API}/analytics/stats/").json()
        self.assertEqual(d["summary"]["results"], 0)
        self.assertEqual(d["groups"], [])
        self.assertEqual(client_for(self.outsider.user).get(f"{API}/analytics/stats/").json()["summary"]["results"], 0)
        self.assertEqual(client_for(make_user("rec", Role.RECEPTIONIST)).get(f"{API}/analytics/stats/").status_code, 403)
