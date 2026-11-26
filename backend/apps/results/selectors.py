from django.db.models import Q

from apps.accounts.models import Role
from apps.examinations.models import ExamKind

from .models import ExamResult


def results_for(user):
    qs = ExamResult.objects.select_related(
        "student__user", "student__current_level", "examination__level", "examination__target_level",
        "examination__created_by", "level", "recommended_level", "placed_level", "attempt", "reviewed_by",
    )
    if user.role == Role.ADMIN:
        return qs
    if user.role == Role.RECEPTIONIST:
        return qs.filter(examination__kind=ExamKind.PLACEMENT)
    if user.role == Role.TEACHER:
        return qs.filter(
            Q(examination__created_by=user) | Q(examination__teachers=user) | Q(student__groups__teacher__user=user)
        ).distinct()
    return qs.filter(student__user=user)
