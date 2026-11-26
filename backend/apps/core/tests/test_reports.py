from django.test import TestCase

from apps.accounts.models import Role
from apps.core.tests.helpers import answer_all, client_for, make_exam, make_levels, make_student, make_user
from apps.examinations.services import create_assignments, start_attempt, submit_attempt

API = "/api/v1"


class ReportTests(TestCase):
    def setUp(self):
        L = make_levels()
        self.admin = make_user("admin", Role.ADMIN)
        self.recep = make_user("recep", Role.RECEPTIONIST)
        self.exam, _ = make_exam(L["B1"], creator=self.admin)
        self.student = make_student("stu", L["B1"])
        create_assignments(examination=self.exam, students=[self.student], assigned_by=self.admin)
        a = self.student.assignments.get()
        attempt = start_attempt(assignment_id=a.id, student=self.student, started_by=self.student.user)
        c = client_for(self.student.user)
        answer_all(c, attempt.id, correct_count=3)
        self.result = submit_attempt(attempt.id)
        self.ac = client_for(self.admin)

    def test_exports_and_filters(self):
        x = self.ac.get(f"{API}/results/export/?file=xlsx")
        self.assertEqual(x.status_code, 200)
        self.assertTrue(x.content.startswith(b"PK"))
        p = self.ac.get(f"{API}/results/export/?file=pdf&level={self.exam.level_id}")
        self.assertTrue(p.content.startswith(b"%PDF"))
        one = self.ac.get(f"{API}/results/{self.result.id}/export/")
        self.assertTrue(one.content.startswith(b"%PDF"))
        self.assertEqual(self.ac.get(f"{API}/results/?passed=false").json()["count"], 0)
        self.assertEqual(self.ac.get(f"{API}/results/?date_from=2000-01-01&teacher={self.admin.id}").json()["count"], 1)

    def test_receptionist_cannot_export(self):
        self.assertEqual(client_for(self.recep).get(f"{API}/results/export/").status_code, 403)

    def test_dashboards_and_stats(self):
        d = self.ac.get(f"{API}/analytics/dashboard/").json()
        self.assertEqual(d["totals"]["attempts"], 1)
        self.assertEqual(d["pass_fail"], {"passed": 1, "failed": 0})
        s = self.ac.get(f"{API}/analytics/results-summary/").json()
        self.assertEqual((s["total"], s["passed"], s["avg_score"], s["avg_max"]), (1, 1, 3.0, 4.0))
        e = self.ac.get(f"{API}/analytics/examinations/{self.exam.id}/").json()
        self.assertEqual(e["completed"], 1)
        self.assertEqual(len(e["questions"]), 4)
        for role_user in (self.recep, self.student.user):
            self.assertEqual(client_for(role_user).get(f"{API}/analytics/dashboard/").status_code, 200)

    def test_student_report_and_admin_detail_has_answer_key(self):
        r = self.ac.get(f"{API}/students/{self.student.id}/report/").json()
        self.assertEqual(len(r["results"]), 1)
        d = self.ac.get(f"{API}/results/{self.result.id}/").json()
        self.assertEqual(len(d["answers"]), 4)
        self.assertEqual(d["answers"][0]["correct_answer"], ["right"])


class TeacherPageTests(TestCase):
    def test_admin_sees_teacher_workload_only_admin(self):
        from apps.academics.models import Group
        from apps.core.tests.helpers import make_student
        from apps.students.models import StudentGroup

        L = make_levels()
        admin, teacher = make_user("admin", Role.ADMIN), make_user("teach", Role.TEACHER)
        g = Group.objects.create(name="G", level=L["B1"], teacher=teacher.teacher_profile)
        StudentGroup.objects.create(student=make_student("s", L["B1"]), group=g)
        make_exam(L["B1"], kind="UPGRADE", target=L["B2"], creator=teacher)
        rows = client_for(admin).get(f"{API}/teachers/").json()["results"]
        self.assertEqual((rows[0]["groups_count"], rows[0]["students_count"], rows[0]["exams_count"]), (1, 1, 1))
        self.assertEqual(client_for(admin).get(f"{API}/teachers/{teacher.id}/").json()["groups"][0]["name"], "G")
        self.assertEqual(client_for(teacher).get(f"{API}/teachers/").status_code, 403)


class ExcelColumnsTests(TestCase):
    def test_section_columns_and_removed_columns(self):
        from io import BytesIO

        from openpyxl import load_workbook

        from apps.academics.models import Level  # noqa: F401
        from apps.core.tests.helpers import answer_all, client_for, make_exam, make_levels, make_student, make_user
        from apps.examinations.services import create_assignments, start_attempt, submit_attempt

        L = make_levels()
        admin = make_user("xadmin", Role.ADMIN)
        student = make_student("xstu", L["A1"])
        exam, _ = make_exam(L["A1"], kind="UPGRADE", target=L["A2"], creator=admin, n=4)
        create_assignments(examination=exam, students=[student], assigned_by=admin)
        attempt = start_attempt(assignment_id=student.assignments.get().id, student=student, started_by=student.user)
        answer_all(client_for(student.user), attempt.id, correct_count=3)
        submit_attempt(attempt.id)
        r = client_for(admin).get("/api/v1/results/export/?file=xlsx")
        self.assertEqual(r.status_code, 200)
        ws = load_workbook(BytesIO(b"".join(r.streaming_content) if hasattr(r, "streaming_content") else r.content)).active
        rows = list(ws.values)
        # the centre's sheet: Number | Full Name | Test | (Writing) | (Speaking) | Overall | Status
        self.assertEqual(list(rows[0]), ["Number", "Full Name", "Test", "Overall", "Status"])  # no writing / speaking part here
        for gone in ("Type", "Phone", "Examination", "Level", "Target", "Approval", "Teacher", "Date", "%"):
            self.assertNotIn(gone, rows[0])
        row = dict(zip(rows[0], rows[1]))
        self.assertEqual((row["Number"], row["Test"], row["Overall"]), (1, 3, 3))  # points
        self.assertIn(row["Status"], ("Passed", "C/Passed", "Failed"))
        pdf = client_for(admin).get("/api/v1/results/export/?file=pdf")
        self.assertEqual(pdf.status_code, 200)
