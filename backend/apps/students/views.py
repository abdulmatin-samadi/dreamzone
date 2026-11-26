from django.db import transaction
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.views import generate_password
from apps.academics.models import Level
from apps.core.exceptions import DomainError
from apps.accounts.models import Role
from apps.core.permissions import IsAdmin, IsAdminOrReceptionist, IsAuthenticated, IsStaffRole, IsAdminOrTeacher

from .models import LevelChangeHistory, StudentProfile
from .selectors import students_for
from .serializers import LevelChangeSerializer, StudentRegisterSerializer, StudentSerializer
from .services import register_student


class StudentViewSet(viewsets.ModelViewSet):
    serializer_class = StudentSerializer
    filterset_fields = {"current_level": ["exact"], "groups": ["exact"]}
    search_fields = ["user__first_name", "user__last_name", "user__phone", "user__username"]
    ordering_fields = ["created_at", "user__first_name", "user__last_name"]

    def get_queryset(self):
        user = self.request.user
        if user.role == Role.TEACHER and self.action == "list" and self.request.query_params.get("available") == "1":
            # students nobody teaches yet: a teacher can find them to add to a group
            return StudentProfile.objects.filter(groups__isnull=True, is_guest=False).select_related(
                "user", "current_level", "initial_level").prefetch_related("groups")
        qs = students_for(user).prefetch_related("groups")
        if self.action == "list":
            qs = qs.filter(is_guest=False)
        if self.request.query_params.get("ungrouped") == "1":
            qs = qs.filter(groups__isnull=True, current_level__isnull=False, is_guest=False)  # placed, but not in a group yet
        return qs

    def get_permissions(self):
        if self.action in ("list", "retrieve", "report"):
            return [IsAuthenticated()]
        if self.action in ("destroy", "set_level"):
            return [IsAdmin()]
        if self.action == "enroll":
            return [IsAdmin()]  # the front desk no longer adds students: they register themselves
        if self.action == "create":
            return [IsAdminOrTeacher()]  # a teacher registers into one of their own groups only
        if self.action == "reset_password":
            return [IsStaffRole()]  # a teacher resets the password of their own students only (the queryset is scoped)  # a teacher may register a student, but only into one of their own groups
        return [IsAdminOrReceptionist()]

    def create(self, request, *args, **kwargs):
        s = StudentRegisterSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        if request.user.role == Role.TEACHER:
            group = s.validated_data.get("group")
            if group is None or group.teacher_id is None or group.teacher.user_id != request.user.id:
                raise DomainError("group_not_accessible", status_code=403)
        profile, password = register_student(registered_by=request.user, **s.validated_data)
        data = StudentSerializer(profile).data
        data["credentials"] = {"username": profile.user.username, "password": password}
        return Response(data, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        """Students with exam history are deactivated, never hard-deleted."""
        from apps.accounts.sessions import revoke
        from apps.audit.services import record

        profile = self.get_object()
        if profile.attempts.exists():
            profile.user.is_active = False
            profile.user.save(update_fields=["is_active"])
            revoke(profile.user.login_sessions.all())
            record("student.deactivated", target=profile)
            return Response({"detail": "deactivated"})
        label, pk_ = profile.user.full_name, profile.pk
        profile.user.delete()
        record("student.deleted", target_type="studentprofile", target_label=label, detail={"id": pk_})
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="reset-password")
    def reset_password(self, request, pk=None):
        from apps.accounts.sessions import revoke
        from apps.audit.services import record

        profile = self.get_object()
        user = profile.user
        password = generate_password()
        user.set_password(password)
        user.save(update_fields=["password"])
        revoke(user.login_sessions.all())
        record("user.password_reset", target=profile)
        return Response({"username": user.username, "password": password})

    @action(detail=True, methods=["post"])
    def enroll(self, request, pk=None):
        """Turn a walk-in 'guest' into a real student (name + phone) and issue login credentials."""
        profile = self.get_object()
        if not profile.is_guest:
            raise DomainError("not_a_guest", status_code=400)
        s = StudentSerializer(profile, data={k: request.data.get(k) for k in ("first_name", "last_name", "phone")}, partial=True)
        s.is_valid(raise_exception=True)
        with transaction.atomic():
            s.save()
            profile.is_guest = False
            profile.save(update_fields=["is_guest"])
            from apps.students.services import _unique_username

            user = profile.user
            user.username = _unique_username(user.phone, user.first_name)
            password = generate_password()
            user.set_password(password)
            user.save()
        return Response({"username": user.username, "password": password})

    @action(detail=True, methods=["post"], url_path="set-level")
    @transaction.atomic
    def set_level(self, request, pk=None):
        from apps.results.services import change_student_level

        student = self.get_object()
        level = Level.objects.filter(pk=request.data.get("level")).first()
        if level is None:
            raise DomainError("level_not_found", status_code=404)
        from apps.audit.services import record

        before = student.current_level.code if student.current_level else None
        change_student_level(student, level, reason=LevelChangeHistory.Reason.ADMIN, changed_by=request.user,
                             note=request.data.get("note", ""))
        record("student.level_changed", target=student, detail={"from": before, "to": level.code, "note": request.data.get("note", "")})
        return Response(StudentSerializer(StudentProfile.objects.get(pk=student.pk)).data)

    @action(detail=True, methods=["get"])
    def report(self, request, pk=None):
        from apps.results.serializers import ResultListSerializer
        from apps.results.selectors import results_for

        student = self.get_object()
        results = results_for(request.user).filter(student=student).select_related(
            "examination", "level", "student__user", "examination__target_level")
        history = student.level_history.select_related("from_level", "to_level", "changed_by", "student__user")
        return Response({
            "student": StudentSerializer(student).data,
            "results": ResultListSerializer(results, many=True).data,
            "level_history": LevelChangeSerializer(history, many=True).data,
        })


class LevelHistoryViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = LevelChangeSerializer
    filterset_fields = ["student", "reason"]

    def get_queryset(self):
        return LevelChangeHistory.objects.filter(
            student__in=students_for(self.request.user)
        ).select_related("student__user", "from_level", "to_level", "changed_by")
