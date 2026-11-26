from django.db.models import Avg, Count, F, Max, Q
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role, User
from apps.academics.models import Group, Level
from apps.core.exceptions import DomainError
from apps.core.permissions import IsAdminOrTeacher
from apps.examinations.models import ExamAssignment, ExamAttempt, ExamKind, Examination, StudentAnswer
from apps.examinations.views import exams_for
from apps.questions.models import Question
from apps.results.filters import ResultFilter
from apps.results.models import ApprovalStatus, ExamResult, OfferStatus
from apps.results.selectors import results_for
from apps.results.serializers import ResultListSerializer
from apps.students.models import StudentProfile
from apps.students.selectors import students_for

from .stats import decided, points


def _g(v):
    return f"{round(v, 1):g}"


def _recent(user, limit=8, **filters):
    qs = results_for(user).filter(**filters)[:limit]
    return ResultListSerializer(qs, many=True).data


def _pass_fail(qs):
    agg = qs.aggregate(n_pass=Count("id", filter=Q(passed=True)), n_fail=Count("id", filter=Q(passed=False)))
    return {"passed": agg["n_pass"], "failed": agg["n_fail"]}


def admin_dashboard(user):
    questions = Question.objects.all()
    by_level = {c: n for c, n in Level.objects.annotate(n=Count("students")).values_list("code", "n")}
    return {
        "totals": {
            "students": StudentProfile.objects.filter(is_guest=False).count(),
            "teachers": User.objects.filter(role=Role.TEACHER).count(),
            "receptionists": User.objects.filter(role=Role.RECEPTIONIST).count(),
            "examinations": Examination.objects.count(),
            "attempts": ExamAttempt.objects.count(),
            "pending_approvals": ExamResult.objects.filter(approval_status=ApprovalStatus.PENDING).count(),
            "writing_pending": ExamResult.objects.filter(writing_pending=True).count(),
        },
        "students_by_level": [{"level": k, "count": v} for k, v in by_level.items()],
        "pass_fail": _pass_fail(ExamResult.objects.all()),
        "recent_results": _recent(user, 10),
        "question_bank": {
            "total": questions.count(),
            "by_section": list(questions.values("section").annotate(count=Count("id")).order_by("section")),
            "by_type": list(questions.values("question_type").annotate(count=Count("id")).order_by("question_type")),
            "by_level": list(
                questions.values(level_code=F("level__code")).annotate(count=Count("id")).order_by("level_code")
            ),
        },
    }



def teacher_dashboard(user):
    students = students_for(user)
    now = timezone.now()
    my_assignments = ExamAssignment.objects.filter(examination__in=exams_for(user))
    pending = results_for(user).filter(approval_status=ApprovalStatus.PENDING)
    schedule = my_assignments.filter(attempt__isnull=True).filter(
        Q(available_from__gte=now) | Q(available_until__gte=now) | Q(available_from__isnull=True, available_until__isnull=True)
    ).select_related("examination", "student__user").order_by("available_from")[:8]
    return {
        "totals": {
            "students": students.count(),
            "groups": Group.objects.filter(teacher__user=user).count(),
            "examinations": exams_for(user).count(),
            "pending_approvals": pending.count(),
            "writing_pending": results_for(user).filter(writing_pending=True, examination__kind=ExamKind.UPGRADE).count(),
        },
        "pass_fail": _pass_fail(results_for(user)),
        "pending_results": ResultListSerializer(pending[:8], many=True).data,
        "recent_results": _recent(user, 8),
        "schedule": [
            {"id": a.id, "examination": a.examination.title, "student": a.student.user.full_name,
             "available_from": a.available_from, "available_until": a.available_until}
            for a in schedule
        ],
    }


def receptionist_dashboard(user):
    today = timezone.localdate()
    placements = ExamAssignment.objects.filter(examination__kind=ExamKind.PLACEMENT)
    return {
        "totals": {
            "registered_today": StudentProfile.objects.filter(created_at__date=today, is_guest=False).count(),
            "waiting": placements.filter(attempt__isnull=True).count(),
            "in_progress": ExamAttempt.objects.filter(examination__kind=ExamKind.PLACEMENT, status="IN_PROGRESS").count(),
            "pending_offers": results_for(user).filter(offer_status=OfferStatus.PENDING).count(),
            "writing_pending": results_for(user).filter(writing_pending=True).count(),
            "awaiting_group": StudentProfile.objects.filter(groups__isnull=True, current_level__isnull=False, is_guest=False).count(),
        },
        "recent_results": _recent(user, 10),
    }


def student_dashboard(user):
    profile = StudentProfile.objects.select_related("current_level").get(user=user)
    assignments = ExamAssignment.objects.filter(student=profile, examination__status="PUBLISHED")
    return {
        "groups": profile.groups.count(),
        "current_level": profile.current_level.code if profile.current_level else None,
        "current_level_name": profile.current_level.name if profile.current_level else None,
        "available": assignments.filter(attempt__isnull=True).count(),
        "completed": ExamResult.objects.filter(student=profile).count(),
        "recent_results": _recent(user, 5),
    }


class DashboardView(APIView):
    def get(self, request):
        fn = {Role.ADMIN: admin_dashboard, Role.TEACHER: teacher_dashboard,
              Role.RECEPTIONIST: receptionist_dashboard, Role.STUDENT: student_dashboard}[request.user.role]
        return Response(fn(request.user))


class ResultsSummaryView(APIView):
    """Pass/fail and average statistics for any filter combination used on the results page."""

    permission_classes = [IsAdminOrTeacher]

    def get(self, request):
        qs = ResultFilter(request.query_params, queryset=results_for(request.user)).qs
        qs = ExamResult.objects.filter(id__in=list(qs.values_list("id", flat=True)))  # no duplicate rows in the aggregates
        done = decided(qs)
        n_done, n_pass = done.count(), done.filter(passed=True).count()
        return Response({
            "total": qs.count(), "decided": n_done, "passed": n_pass, "failed": n_done - n_pass,
            "awaiting": qs.count() - n_done, **points(qs.filter(writing_pending=False)),
        })


class ExaminationStatsView(APIView):
    permission_classes = [IsAdminOrTeacher]

    def get(self, request, pk):
        exam = exams_for(request.user).filter(pk=pk).first()
        if exam is None:
            raise DomainError("not_found", status_code=404)
        results = ExamResult.objects.filter(examination=exam)
        done = decided(results)
        n_done, n_pass = done.count(), done.filter(passed=True).count()
        # score distribution in points: ten equal bands of the exam's maximum
        top = float(results.aggregate(m=Max("max_score"))["m"] or 0)
        step = top / 10 if top else 1
        buckets = [0] * 10
        for score in results.values_list("total_score", flat=True):
            buckets[min(int(float(score) // step), 9)] += 1
        sections = {}
        for r in results.values_list("section_scores", flat=True):
            for name, s in r.items():
                acc = sections.setdefault(name, [0.0, 0.0])
                acc[0] += s["score"]
                acc[1] += s["max"]
        per_question = list(
            StudentAnswer.objects.filter(attempt__examination=exam).values("question_id", text=F("question__text"))
            .annotate(answered=Count("id"), correct=Count("id", filter=Q(is_correct=True))).order_by("question_id")
        )
        return Response({
            "examination": exam.title, "attempts": exam.attempts.count(), "completed": results.count(),
            "decided": n_done, "passed": n_pass, "failed": n_done - n_pass, "awaiting": results.count() - n_done,
            **points(results.filter(writing_pending=False)), "max_score": round(top, 1),
            "distribution": [{"range": f"{_g(i * step)}–{_g((i + 1) * step)}", "count": c} for i, c in enumerate(buckets)] if top else [],
            "sections": [{"section": k, "score": round(v[0], 1), "max": round(v[1], 1)} for k, v in sections.items()],
            "questions": [
                {**q, "percentage_correct": round(q["correct"] / q["answered"] * 100, 1) if q["answered"] else 0}
                for q in per_question
            ],
        })
