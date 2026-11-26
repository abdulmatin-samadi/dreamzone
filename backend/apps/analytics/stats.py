"""Personal statistics: a student's own progress, a teacher's (or admin's) class overview.

Results whose written part still waits for the teacher are provisional: they are counted,
but kept out of averages, pass rates and section scores until they are graded.
"""
from django.db.models import Avg, Count, Max, Q
from django.db.models.functions import TruncMonth
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role
from apps.academics.models import Group
from apps.core.exceptions import DomainError
from apps.examinations.models import ExamKind
from apps.results.models import ApprovalStatus, ExamResult
from apps.results.serializers import awaiting_decision
from apps.results.selectors import results_for
from apps.students.models import StudentProfile


def _r(value, nd=1):
    return round(float(value), nd) if value is not None else None


def decided(qs):
    """Results with a final verdict: written part scored and, for upgrades, the teacher / admin has decided."""
    return qs.filter(writing_pending=False).exclude(examination__kind=ExamKind.UPGRADE, approval_status=ApprovalStatus.PENDING)


def points(qs):
    """Average score and average maximum, in points."""
    agg = qs.aggregate(s=Avg("total_score"), m=Avg("max_score"))
    return {"avg_score": _r(agg["s"]), "avg_max": _r(agg["m"])}


def summary(qs):
    final = qs.filter(writing_pending=False)
    done = decided(qs)
    total = done.count()
    n_pass = done.filter(passed=True).count()
    best = final.order_by("-percentage", "-total_score").first()
    return {
        "results": qs.count(), "graded": total, "passed": n_pass, "failed": total - n_pass,
        **points(final),
        "best_score": _r(best.total_score) if best else None, "best_max": _r(best.max_score) if best else None,
        "awaiting": qs.count() - total - qs.filter(writing_pending=True).count(),
        "writing_pending": qs.filter(writing_pending=True).count(),
    }


def sections(qs):
    """Sum of points per section over the graded results -> where the student / class is strong or weak."""
    acc = {}
    for scores in qs.filter(writing_pending=False).values_list("section_scores", flat=True):
        for name, s in (scores or {}).items():
            a = acc.setdefault(name, [0.0, 0.0])
            a[0] += float(s.get("score") or 0)
            a[1] += float(s.get("max") or 0)
    rows = [{"section": k, "score": _r(v[0], 2), "max": _r(v[1], 2)} for k, v in acc.items() if v[1]]
    return sorted(rows, key=lambda r: r["score"] / r["max"], reverse=True)


def monthly(qs, months=12):
    rows = (qs.filter(writing_pending=False).annotate(m=TruncMonth("created_at")).values("m")
            .annotate(n=Count("id"), s=Avg("total_score"), mx=Avg("max_score"), n_pass=Count("id", filter=Q(passed=True))).order_by("-m")[:months])
    return [{"month": r["m"].strftime("%Y-%m"), "results": r["n"], "avg_score": _r(r["s"]), "avg_max": _r(r["mx"]), "passed": r["n_pass"]}
            for r in reversed(rows)]


def student_stats(user):
    profile = StudentProfile.objects.select_related("current_level", "initial_level").filter(user=user).first()
    if profile is None:
        raise DomainError("not_found", status_code=404)
    qs = ExamResult.objects.filter(student=profile).select_related("examination")
    timeline = [
        {"id": r.id, "date": r.created_at, "examination": r.examination.title, "kind": r.examination.kind,
         "score": _r(r.total_score), "max": _r(r.max_score),
         "passed": None if awaiting_decision(r) else r.passed, "writing_pending": r.writing_pending}
        for r in qs.order_by("created_at")[:50]
    ]
    return {
        "role": Role.STUDENT, "summary": summary(qs), "sections": sections(qs), "timeline": timeline,
        "level": {"current": profile.current_level.code if profile.current_level else None,
                  "initial": profile.initial_level.code if profile.initial_level else None},
    }


def staff_stats(user):
    # ids first: results_for() joins through groups and may repeat a row, aggregates must not
    base = ExamResult.objects.filter(id__in=list(results_for(user).values_list("id", flat=True)))
    groups = Group.objects.select_related("level").order_by("name")
    if user.role == Role.TEACHER:
        groups = groups.filter(teacher__user=user)
    by_group = []
    for g in groups:
        gq = base.filter(student__memberships__group=g)
        s = summary(gq)
        by_group.append({"id": g.id, "name": g.name, "level": g.level.code, "students": g.memberships.count(),
                         "results": s["results"], "avg_score": s["avg_score"], "avg_max": s["avg_max"],
                         "passed": s["passed"], "graded": s["graded"]})
    per_student = list(
        base.filter(writing_pending=False).values("student_id", "student__user__first_name", "student__user__last_name")
        .annotate(n=Count("id"), avg=Avg("percentage"), s=Avg("total_score"), mx=Avg("max_score"),
                  n_pass=Count("id", filter=Q(passed=True)), last=Max("created_at"))
        .order_by("-avg")
    )
    students = [{"id": r["student_id"], "name": f'{r["student__user__first_name"]} {r["student__user__last_name"]}'.strip(),
                 "results": r["n"], "avg_score": _r(r["s"]), "avg_max": _r(r["mx"]), "pct": _r(r["avg"]),
                 "passed": r["n_pass"], "last": r["last"]} for r in per_student]
    exams = [
        {"id": r["examination_id"], "title": r["examination__title"], "kind": r["examination__kind"], "results": r["n"],
         "avg_score": _r(r["s"]), "avg_max": _r(r["mx"]), "passed": r["n_pass"]}
        for r in base.filter(writing_pending=False).values("examination_id", "examination__title", "examination__kind")
        .annotate(n=Count("id"), s=Avg("total_score"), mx=Avg("max_score"), n_pass=Count("id", filter=Q(passed=True))).order_by("-n")[:10]
    ]
    return {
        "role": user.role, "summary": summary(base), "sections": sections(base), "monthly": monthly(base),
        "groups": by_group, "top_students": students[:5],
        "attention": [s for s in reversed(students) if s["pct"] is not None and s["pct"] < 50][:5],
        "exams": exams,
    }


class StatsView(APIView):
    def get(self, request):
        role = request.user.role
        if role == Role.STUDENT:
            return Response(student_stats(request.user))
        if role in (Role.TEACHER, Role.ADMIN):
            return Response(staff_stats(request.user))
        raise DomainError("forbidden", status_code=403)
