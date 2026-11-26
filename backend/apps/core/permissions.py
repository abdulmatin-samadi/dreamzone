from rest_framework.permissions import BasePermission

from apps.accounts.models import Role


def kiosk_allows(request, view):
    """Kiosk tokens (issued to the receptionist so a walk-in student can sit the
    placement test) may only be used on views that opt in with ``kiosk_ok = True``."""
    token = request.auth
    if token is not None and hasattr(token, "get") and token.get("kiosk"):
        return bool(getattr(view, "kiosk_ok", False))
    return True


class IsAuthenticated(BasePermission):
    """Authenticated + kiosk-token restriction. Used everywhere instead of DRF's class."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and kiosk_allows(request, view))


def role_permission(*roles):
    class _RolePermission(BasePermission):
        def has_permission(self, request, view):
            u = request.user
            return bool(u and u.is_authenticated and u.role in roles and kiosk_allows(request, view))

    _RolePermission.__name__ = "Is" + "Or".join(r.title() for r in roles)
    return _RolePermission


IsAdmin = role_permission(Role.ADMIN)
IsReceptionist = role_permission(Role.RECEPTIONIST)
IsTeacher = role_permission(Role.TEACHER)
IsStudent = role_permission(Role.STUDENT)
IsAdminOrTeacher = role_permission(Role.ADMIN, Role.TEACHER)
IsAdminOrReceptionist = role_permission(Role.ADMIN, Role.RECEPTIONIST)
IsTeacherOrReceptionist = role_permission(Role.TEACHER, Role.RECEPTIONIST)
IsStaffRole = role_permission(Role.ADMIN, Role.TEACHER, Role.RECEPTIONIST)
