from django.test import TestCase

from apps.accounts.models import Role
from apps.academics.models import Group
from apps.core.tests.helpers import answer_all, client_for, make_exam, make_levels, make_student, make_user
from apps.examinations.models import ExamAssignment, ExamKind, GroupExam
from apps.students.models import StudentGroup

API = "/api/v1"


class AdminGivesExamToGroupsTests(TestCase):
    """Admin gives an upgrade exam to groups only; the group's teacher then picks the students."""

    def setUp(self):
        self.L = make_levels()
        self.admin = make_user("admin", Role.ADMIN)
        self.teacher = make_user("teach", Role.TEACHER)
        self.other = make_user("teach2", Role.TEACHER)
        self.group = Group.objects.create(name="G1", level=self.L["B1"], teacher=self.teacher.teacher_profile)
        self.other_group = Group.objects.create(name="G2", level=self.L["B1"], teacher=self.teacher.teacher_profile)
        self.a2_group = Group.objects.create(name="A2 group", level=self.L["A2"], teacher=self.other.teacher_profile)
        self.s1, self.s2, self.s3 = (make_student(n, self.L["B1"]) for n in ("s1", "s2", "s3"))
        StudentGroup.objects.create(student=self.s1, group=self.group)
        StudentGroup.objects.create(student=self.s2, group=self.group)
        StudentGroup.objects.create(student=self.s3, group=self.other_group)  # same teacher, group not given the exam
        self.exam, self.variant = make_exam(self.L["B1"], kind=ExamKind.UPGRADE, target=self.L["B2"], creator=self.admin)
        self.ac, self.tc = client_for(self.admin), client_for(self.teacher)
        self.url = f"{API}/examinations/{self.exam.id}/assign/"

    def test_giving_to_a_group_gives_it_to_every_student_of_the_group(self):
        r = self.ac.post(self.url, {"student_ids": [self.s1.id]}, format="json")
        self.assertEqual(r.json()["code"], "admin_assigns_groups")
        r = self.ac.post(self.url, {"group_ids": [self.group.id, self.a2_group.id]}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        out = r.json()
        self.assertEqual((out["groups_added"], [m["name"] for m in out["groups_level_mismatch"]]), (1, ["A2 group"]))
        self.assertTrue(GroupExam.objects.filter(examination=self.exam, group=self.group).exists())
        # everyone in G1 has it now, nobody outside it
        self.assertEqual(out["students_assigned"], 2)
        self.assertEqual(set(ExamAssignment.objects.values_list("student_id", flat=True)), {self.s1.id, self.s2.id})
        self.assertEqual(self.ac.post(self.url, {"group_ids": [self.group.id]}, format="json").json()["groups_existing"], 1)
        self.assertEqual(ExamAssignment.objects.count(), 2)  # never twice
        # whoever joins G1 later gets it too - being in the group counts, not the level on the profile
        late, other_level = make_student("late", self.L["B1"]), make_student("a2", self.L["A2"])
        StudentGroup.objects.create(student=late, group=self.group)
        StudentGroup.objects.create(student=other_level, group=self.group)
        self.assertTrue(ExamAssignment.objects.filter(student=late, examination=self.exam, group=self.group).exists())
        self.assertTrue(ExamAssignment.objects.filter(student=other_level, examination=self.exam).exists())

    def test_admin_can_also_assign_straight_to_students(self):
        r = self.ac.post(self.url, {"to": "students", "student_ids": [self.s3.id]}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["created"], 1)
        self.assertEqual(list(ExamAssignment.objects.values_list("student_id", flat=True)), [self.s3.id])
        self.assertFalse(GroupExam.objects.exists())  # no group grant was made

    def test_teacher_sees_it_assigns_own_group_students_but_cannot_edit(self):
        self.assertEqual(self.tc.get(f"{API}/examinations/{self.exam.id}/").status_code, 404)  # not given yet
        self.ac.post(self.url, {"group_ids": [self.group.id]}, format="json")
        r = self.tc.get(f"{API}/examinations/{self.exam.id}/")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["can_edit"])
        self.assertEqual(self.tc.get(f"{API}/variants/?examination={self.exam.id}").status_code, 200)
        # read only: no settings, publishing, deleting or question changes
        self.assertEqual(self.tc.patch(f"{API}/examinations/{self.exam.id}/", {"title": "x"}, format="json").status_code, 404)
        self.assertEqual(self.tc.post(f"{API}/examinations/{self.exam.id}/unpublish/").status_code, 404)
        self.assertEqual(self.tc.delete(f"{API}/examinations/{self.exam.id}/").status_code, 404)
        self.assertEqual(self.tc.delete(f"{API}/variants/{self.variant.id}/").status_code, 404)
        # a student of a group that did not get the exam is refused; the given group's students already have it
        self.assertEqual(self.tc.post(self.url, {"student_ids": [self.s3.id]}, format="json").status_code, 403)
        self.assertEqual(self.tc.post(self.url, {"group_ids": [self.other_group.id]}, format="json").status_code, 403)
        r = self.tc.post(self.url, {"student_ids": [self.s1.id]}, format="json")
        self.assertEqual((r.status_code, r.json()["created"], r.json()["skipped_existing"]), (201, 0, 1))
        rows = self.tc.get(f"{API}/examinations/{self.exam.id}/groups/").json()
        self.assertEqual([(x["name"], x["students"], x["assigned"]) for x in rows], [("G1", 2, 2)])
        # another teacher sees nothing
        self.assertEqual(client_for(self.other).get(f"{API}/examinations/{self.exam.id}/").status_code, 404)

    def test_admin_sees_group_progress_in_points_and_student_never_sees_answers(self):
        self.exam.show_correct_answers = True
        self.exam.save()
        self.ac.post(self.url, {"group_ids": [self.group.id]}, format="json")
        self.tc.post(self.url, {"group_ids": [self.group.id]}, format="json")  # teacher: the whole group
        c = client_for(self.s1.user)
        a = c.get(f"{API}/my/assignments/").json()[0]
        self.assertEqual((a["max_points"], a["passing_points"]), (4.0, 2.0))  # 4 one-point questions, pass mark 50%
        attempt = c.post(f"{API}/assignments/{a['id']}/start/").json()
        answer_all(c, attempt["id"], correct_count=3)
        rid = c.post(f"{API}/attempts/{attempt['id']}/submit/").json()["result_id"]
        self.assertIsNone(c.get(f"{API}/results/{rid}/").json()["answers"])  # even when the exam allowed it
        self.assertEqual(len(self.tc.get(f"{API}/results/{rid}/").json()["answers"]), 4)

        self.assertEqual(self.tc.get(f"{API}/analytics/group-exams/").status_code, 403)
        rows = self.ac.get(f"{API}/analytics/group-exams/").json()
        self.assertEqual(len(rows), 1)
        g = rows[0]
        self.assertEqual((g["group_name"], g["status"], g["assigned"], g["finished"], g["waiting"], g["average"], g["max"]),
                         ("G1", "in_progress", 2, 1, 1, 3.0, 4.0))
        self.assertEqual({m["name"]: (m["state"], m["score"]) for m in g["members"]},
                         {self.s1.user.full_name: ("finished", 3.0), self.s2.user.full_name: ("waiting", None)})

    def test_admin_takes_it_back(self):
        self.ac.post(self.url, {"group_ids": [self.group.id]}, format="json")
        self.assertEqual(self.tc.post(f"{API}/examinations/{self.exam.id}/revoke-group/", {"group": self.group.id}).status_code, 403)
        self.assertEqual(self.ac.post(f"{API}/examinations/{self.exam.id}/revoke-group/", {"group": self.group.id}).status_code, 204)
        self.assertEqual(self.tc.get(f"{API}/examinations/{self.exam.id}/").status_code, 404)


class SpeakingTests(TestCase):
    """Teacher / admin enter the speaking score on the result; it is added to the total in points."""

    def setUp(self):
        self.L = make_levels()
        self.admin = make_user("admin", Role.ADMIN)
        self.teacher = make_user("teach", Role.TEACHER)
        group = Group.objects.create(name="G1", level=self.L["B1"], teacher=self.teacher.teacher_profile)
        self.s = make_student("s1", self.L["B1"])
        StudentGroup.objects.create(student=self.s, group=group)
        self.exam, _ = make_exam(self.L["B1"], kind=ExamKind.UPGRADE, target=self.L["B2"], creator=self.admin,
                                 passing=8, speaking_points=10)  # 4 one-point questions + 10 speaking
        ac = client_for(self.admin)
        ac.post(f"{API}/examinations/{self.exam.id}/assign/", {"to": "students", "student_ids": [self.s.id]}, format="json")
        c = client_for(self.s.user)
        a = c.get(f"{API}/my/assignments/").json()[0]
        attempt = c.post(f"{API}/assignments/{a['id']}/start/").json()
        answer_all(c, attempt["id"], correct_count=3)
        self.rid = c.post(f"{API}/attempts/{attempt['id']}/submit/").json()["result_id"]
        self.sc, self.ac, self.tc = c, ac, client_for(self.teacher)

    def test_speaking_added_to_total_and_required_before_decision(self):
        url = f"{API}/results/{self.rid}/"
        self.assertEqual(self.tc.post(url + "approve/").json()["code"], "speaking_still_pending")
        self.assertEqual(self.sc.post(url + "speaking/", {"points": 5}).status_code, 403)  # not the student
        self.assertEqual(self.tc.post(url + "speaking/", {"points": 11}).json()["code"], "points_out_of_range")
        d = self.tc.post(url + "speaking/", {"points": 6, "feedback": "Good fluency"}).json()
        self.assertEqual((float(d["total_score"]), float(d["max_score"])), (9.0, 14.0))  # 3 + 6 of 4 + 10
        self.assertTrue(d["passed"])  # suggestion: 9 >= 8
        self.assertEqual(d["section_scores"]["SPEAKING"]["score"], 6.0)
        d = self.ac.post(url + "speaking/", {"points": 4}).json()  # the admin corrects it
        self.assertEqual((float(d["total_score"]), d["passed"]), (7.0, False))
        self.assertEqual(self.tc.post(url + "reject/").status_code, 200)
        self.assertEqual(self.tc.post(url + "speaking/", {"points": 9}).json()["code"], "result_locked")

    def test_exam_without_speaking_points_takes_the_max_from_the_reviewer(self):
        self.exam.speaking_points = 0
        self.exam.save()
        url = f"{API}/results/{self.rid}/speaking/"
        self.assertEqual(self.tc.post(url, {"points": 5}).json()["code"], "speaking_not_set")
        d = self.tc.post(url, {"points": 5, "max": 10}).json()
        self.assertEqual((float(d["total_score"]), float(d["max_score"]), float(d["speaking_max"])), (8.0, 14.0, 10.0))
        self.assertEqual(self.tc.post(f"{API}/results/{self.rid}/approve/").status_code, 200)  # no speaking required

    def test_paper_writing_points_added_and_required_before_decision(self):
        self.exam.writing_points = 20
        self.exam.save()
        url = f"{API}/results/{self.rid}/"
        self.tc.post(url + "speaking/", {"points": 6})
        self.assertEqual(self.tc.post(url + "approve/").json()["code"], "writing_score_pending")
        self.assertEqual(self.sc.post(url + "writing-score/", {"points": 5}).status_code, 403)  # not the student
        self.assertEqual(self.tc.post(url + "writing-score/", {"points": 21}).json()["code"], "points_out_of_range")
        d = self.tc.post(url + "writing-score/", {"points": 15, "feedback": "Good ideas"}).json()
        self.assertEqual((float(d["total_score"]), float(d["max_score"])), (24.0, 34.0))  # 3 + 6 + 15 of 4 + 10 + 20
        self.assertEqual((d["section_scores"]["WRITING"]["score"], d["section_scores"]["SPEAKING"]["score"]), (15.0, 6.0))
        mine = self.sc.get(url).json()
        self.assertEqual((mine["writing_score"], mine["writing_points"]), (None, None))  # the student sees no points
        self.assertEqual(self.tc.post(url + "approve/").status_code, 200)


class JoinByCodeTests(TestCase):
    """A student who types the group code gets the exams given to that group - no level needed."""

    def test_student_without_level_joins_by_code_and_gets_the_group_exam(self):
        L = make_levels()
        admin = make_user("admin", Role.ADMIN)
        group = Group.objects.create(name="Beginner", level=L["A1"])
        exam, _ = make_exam(L["A1"], kind=ExamKind.UPGRADE, target=L["A2"], creator=admin)
        client_for(admin).post(f"{API}/examinations/{exam.id}/assign/", {"group_ids": [group.id]}, format="json")
        st = make_student("newbie", None)  # registered by themselves: no level on the profile
        c = client_for(st.user)
        self.assertFalse(ExamAssignment.objects.filter(student=st).exists())  # nothing before joining
        self.assertEqual(c.post(f"{API}/groups/join/", {"code": group.join_code}).status_code, 201)
        mine = c.get(f"{API}/my/assignments/").json()
        rows = mine["results"] if isinstance(mine, dict) else mine
        self.assertEqual([a["examination_title"] for a in rows], [exam.title])
        # sits it, the teacher / admin passes it -> moved up even though no level was set before
        attempt = c.post(f"{API}/assignments/{rows[0]['id']}/start/").json()
        answer_all(c, attempt["id"], correct_count=4)
        rid = c.post(f"{API}/attempts/{attempt['id']}/submit/").json()["result_id"]
        self.assertEqual(client_for(admin).post(f"{API}/results/{rid}/approve/").status_code, 200)
        st.refresh_from_db()
        self.assertEqual(st.current_level.code, "A2")


class ShuffleTests(TestCase):
    """Different students get a different order, but each exercise stays together and reading follows its text."""

    def test_order_differs_per_student_inside_exercises(self):
        from apps.examinations.services import _build_layout
        from apps.questions.models import Passage

        L = make_levels()
        admin = make_user("admin", Role.ADMIN)
        exam, variant = make_exam(L["A1"], kind=ExamKind.UPGRADE, target=L["A2"], creator=admin, n=12)
        self.assertTrue(exam.shuffle_questions and exam.shuffle_options)  # on by default
        vqs = list(variant.variant_questions.select_related("question").order_by("order"))
        for vq in vqs[:6]:
            vq.question.category, vq.question.instruction = "MCQ", "Choose"
            vq.question.save()
        p = Passage.objects.create(title="T", text="text", level=L["A1"])
        for vq in vqs[6:]:
            vq.question.passage = p
            vq.question.save()
        first, reading = [vq.question_id for vq in vqs[:6]], [vq.question_id for vq in vqs[6:]]
        orders = {tuple(_build_layout(f"attempt-{i}", exam, variant)["questions"]) for i in range(20)}
        self.assertGreater(len(orders), 1)  # not the same for everyone
        for o in orders:
            self.assertEqual(sorted(o[:6]), sorted(first))  # the exercise stays together, first
            self.assertEqual(list(o[6:]), reading)          # reading keeps the text's order
