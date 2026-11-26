from apps.accounts.models import Role

from .models import StudentProfile


def students_for(user):
    """Students a given user is allowed to see (teachers only see their own groups' students)."""
    qs = StudentProfile.objects.select_related("user", "current_level", "initial_level")
    if user.role in (Role.ADMIN, Role.RECEPTIONIST):
        return qs
    if user.role == Role.TEACHER:
        return qs.filter(groups__teacher__user=user).distinct()
    return qs.filter(user=user)
