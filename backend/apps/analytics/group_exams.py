"""Which groups are sitting / have sat which upgrade exam - per group progress and every student's score in points."""
from collections import defaultdict

from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.models import Group
from apps.core.permissions import IsAdmin
from apps.results.serializers import awaiting_decision
from apps.examinations.models import ExamAssignment, ExamKind, Examination, GroupExam


def _num(v):
    return float(v) if v is not None else None


def _student_state(assignment):
    """not_assigned / waiting (not started) / in_progress (started, incl. stopped for a teacher) / finished (has a result)."""
    if assignment is None:
        return "not_assigned"
    attempt = assignment.attempt if hasattr(assignment, "attempt") else None
    if attempt is None:
        return "waiting"
    return "finished" if hasattr(attempt, "result") else "in_progress"


def group_exam_progress():
    pairs = defaultdict(set)  # exam id -> group ids
    for e, g in GroupExam.objects.values_list("examination_id", "group_id"):
        pairs[e].add(g)
    upgrade = ExamAssignment.objects.filter(examination__kind=ExamKind.UPGRADE)
    for e, g in upgrade.filter(group__isnull=False).values_list("examination_id", "group_id"):
        pairs[e].add(g)
    # assigned one by one (by the teacher or the admin): counts for the group the student is in
    for e, g in upgrade.filter(group__isnull=True, student__groups__isnull=False).values_list("examination_id", "student__groups__id"):
        pairs[e].add(g)
    if not pairs:
        return []

    exams = Examination.objects.in_bulk(list(pairs))
    groups = Group.objects.select_related("level", "teacher__user").prefetch_related("students__user").in_bulk(
        {g for gs in pairs.values() for g in gs})
    assignments = {
        (a.examination_id, a.student_id): a
        for a in upgrade.filter(examination_id__in=list(pairs)).select_related("attempt__result")
    }
    granted = set(GroupExam.objects.values_list("examination_id", "group_id"))

    rows = []
    for exam_id, group_ids in pairs.items():
        exam = exams[exam_id]
        for gid in group_ids:
            g = groups.get(gid)
            if g is None:
                continue
            members, counts, scores = [], defaultdict(int), []
            for st in sorted(g.students.all(), key=lambda s: s.user.full_name):
                a = assignments.get((exam_id, st.id))
                state = _student_state(a)
                counts[state] += 1
                r = getattr(a.attempt, "result", None) if a is not None and hasattr(a, "attempt") else None
                m = {"student_id": st.id, "name": st.user.full_name, "state": state, "result_id": r.id if r else None,
                     "score": _num(r.total_score) if r else None, "max": _num(r.max_score) if r else None,
                     "passed": r.passed if r else None, "writing_pending": r.writing_pending if r else False,
                     "awaiting": awaiting_decision(r) if r else False,
                     "approval_status": r.approval_status if r else None,
                     "correct": r.correct_count if r else None, "incorrect": r.incorrect_count if r else None,
                     "unanswered": r.unanswered_count if r else None, "finished_at": r.created_at if r else None,
                     "sections": r.section_scores if r else None}
                if r:
                    scores.append((float(r.total_score), float(r.max_score), r.passed and not awaiting_decision(r)))
                members.append(m)
            assigned = len(members) - counts["not_assigned"]
            if not assigned and (exam_id, gid) not in granted:
                continue  # the students who had it left the group
            finished = counts["finished"]
            if assigned and finished == assigned:
                status = "finished"
            elif finished or counts["in_progress"]:
                status = "in_progress"
            else:
                status = "waiting"
            rows.append({
                "exam_id": exam.id, "exam_title": exam.title, "group_id": g.id, "group_name": g.name, "level": g.level.code,
                "teacher": g.teacher.user.full_name if g.teacher_id else None, "status": status,
                "students": len(members), "assigned": assigned, "waiting": counts["waiting"], "in_progress": counts["in_progress"],
                "finished": finished, "passed": sum(1 for s in scores if s[2]),
                "average": round(sum(s[0] for s in scores) / len(scores), 1) if scores else None,
                "max": max((s[1] for s in scores), default=None),
                "members": members,
            })
    order = {"in_progress": 0, "waiting": 1, "finished": 2}
    rows.sort(key=lambda r: (order[r["status"]], r["exam_title"], r["group_name"]))
    return rows


class GroupExamProgressView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        return Response(group_exam_progress())
