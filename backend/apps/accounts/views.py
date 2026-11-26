import secrets

from django.db.models import ProtectedError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import RetrieveUpdateAPIView
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.core.exceptions import DomainError
from apps.core.permissions import IsAdmin

from .models import Role, User
from .serializers import ChangePasswordSerializer, ChangeUsernameSerializer, LoginSerializer, MeSerializer, UserSerializer


def generate_password(length=8):
    alphabet = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


class LoginView(TokenObtainPairView):
    serializer_class = LoginSerializer
    permission_classes = []
    authentication_classes = []
    throttle_scope = "login"


class CaptchaView(APIView):
    """A fresh "I am not a robot" picture for the registration form."""

    permission_classes = []
    authentication_classes = []
    throttle_scope = "captcha"

    def get(self, request):
        from .verification import make_captcha

        token, image, _answer = make_captcha()
        return Response({"token": token, "image": image})


class RegisterView(APIView):
    """Self-registration: robot check + details. Creates the account right away and signs the
    student in (no test is assigned automatically). The e-mail address is the login."""

    permission_classes = []
    authentication_classes = []
    throttle_scope = "register"

    def post(self, request):
        from django.contrib.auth import password_validation
        from django.db import transaction
        from django.db.models import Q
        from rest_framework import serializers as drf

        from apps.academics.models import Level
        from apps.students.services import register_student

        from .verification import check_captcha

        class Body(drf.Serializer):
            first_name = drf.CharField(max_length=150)
            last_name = drf.CharField(max_length=150)
            username = drf.CharField(min_length=3, max_length=150)
            password = drf.CharField(write_only=True)
            initial_level = drf.PrimaryKeyRelatedField(queryset=Level.objects.filter(is_active=True), required=False, allow_null=True)
            captcha_token = drf.CharField()
            captcha_answer = drf.CharField(max_length=12)
            website = drf.CharField(required=False, allow_blank=True)  # honeypot: people never see it

        s = Body(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        if d.get("website"):
            raise DomainError("captcha_invalid", status_code=400)
        if not check_captcha(d["captcha_token"], d["captcha_answer"]):
            raise DomainError("captcha_invalid", status_code=400)
        from django.contrib.auth.validators import UnicodeUsernameValidator
        from django.core.exceptions import ValidationError as DjangoValidationError

        username = d["username"].strip().lower()
        try:
            UnicodeUsernameValidator()(username)  # letters, digits and @ . + - _ only
        except DjangoValidationError:
            raise drf.ValidationError({"username": ["username_invalid"]})
        taken = lambda: User.objects.filter(Q(username__iexact=username) | Q(email__iexact=username)).exists()  # noqa: E731
        if taken():
            raise drf.ValidationError({"username": ["username_taken"]})
        first_name = d["first_name"].strip()
        try:
            password_validation.validate_password(d["password"], User(username=username, first_name=first_name))
        except Exception as exc:  # DjangoValidationError
            raise drf.ValidationError({"password": list(getattr(exc, "messages", [str(exc)]))})
        with transaction.atomic():
            if taken():
                raise drf.ValidationError({"username": ["username_taken"]})
            profile, _ = register_student(first_name=first_name, last_name=d["last_name"].strip(), phone="",
                                          initial_level=d.get("initial_level"), registered_by=None)
            user = profile.user
            user.username = username
            user.set_password(d["password"])
            user.save(update_fields=["username", "password"])
            # no test is given automatically: a student gets exams through reception / the admin / their group
        from .sessions import start_session

        refresh, _session = start_session(user, request)
        return Response({"access": str(refresh.access_token), "refresh": str(refresh),
                         "user": MeSerializer(user).data, "username": user.username}, status=status.HTTP_201_CREATED)


class PublicLevelsView(APIView):
    """Levels offered on the public registration form (only those with an active placement test)."""

    permission_classes = []
    authentication_classes = []

    def get(self, request):
        from apps.academics.models import Level

        levels = Level.objects.filter(is_active=True, examinations__kind="PLACEMENT", examinations__status="PUBLISHED")
        return Response([{"id": l.id, "code": l.code, "name": l.name} for l in levels.distinct()])


class LogoutView(APIView):
    def post(self, request):
        from .models import LoginSession
        from .sessions import revoke

        try:
            token = RefreshToken(request.data.get("refresh", ""))
            sid = token.get("sid")
            token.blacklist()
        except TokenError:
            sid = None
        sid = sid or (request.auth.get("sid") if request.auth is not None and hasattr(request.auth, "get") else None)
        if sid:
            revoke(LoginSession.objects.filter(pk=sid, user=request.user))
        return Response(status=status.HTTP_204_NO_CONTENT)


def _current_sid(request):
    token = request.auth
    return str(token.get("sid")) if token is not None and hasattr(token, "get") and token.get("sid") else None


def _session_rows(sessions, current_sid=None):
    from .sessions import describe_agent

    return [{
        "id": str(s.id), "device": describe_agent(s.user_agent), "device_name": s.device_name, "ip": s.ip,
        "created_at": s.created_at, "last_seen_at": s.last_seen_at, "current": str(s.id) == current_sid,
    } for s in sessions]


class SessionsView(APIView):
    """The devices I am signed in on."""

    def get(self, request):
        from .sessions import active_sessions

        return Response(_session_rows(active_sessions(request.user), _current_sid(request)))


class SessionRevokeView(APIView):
    def post(self, request, sid):
        from apps.audit.services import record

        from .sessions import active_sessions, revoke

        n = revoke(active_sessions(request.user).filter(pk=sid))
        if not n:
            raise DomainError("session_not_found", status_code=404)
        record("session.revoked", target=request.user, detail={"count": 1})
        return Response({"revoked": n})


class SessionRevokeOthersView(APIView):
    """'Sign out on every other device' (this one stays signed in)."""

    def post(self, request):
        from apps.audit.services import record

        from .sessions import active_sessions, revoke

        qs = active_sessions(request.user)
        current = _current_sid(request)
        if current:
            qs = qs.exclude(pk=current)
        n = revoke(qs)
        record("session.revoked_all", target=request.user, detail={"count": n})
        return Response({"revoked": n})


class MeView(RetrieveUpdateAPIView):
    serializer_class = MeSerializer
    http_method_names = ["get", "patch", "head", "options"]

    def get_object(self):
        return self.request.user


class ChangePasswordView(APIView):
    def post(self, request):
        s = ChangePasswordSerializer(data=request.data, context={"request": request})
        s.is_valid(raise_exception=True)
        from .sessions import active_sessions, revoke

        request.user.set_password(s.validated_data["new_password"])
        request.user.save(update_fields=["password"])
        others = active_sessions(request.user)
        if _current_sid(request):
            others = others.exclude(pk=_current_sid(request))
        revoke(others)  # a new password signs the other devices out
        return Response({"detail": "ok"})


class ChangeUsernameView(APIView):
    def post(self, request):
        s = ChangeUsernameSerializer(data=request.data, context={"request": request})
        s.is_valid(raise_exception=True)
        request.user.username = s.validated_data["username"]
        request.user.save(update_fields=["username"])
        return Response(MeSerializer(request.user).data)


class TeacherViewSet(viewsets.ReadOnlyModelViewSet):
    """Admin overview of teachers with workload numbers. Create / edit goes through /users/."""

    permission_classes = [IsAdmin]
    filterset_fields = ["is_active"]
    search_fields = ["first_name", "last_name", "username", "phone"]
    ordering_fields = ["first_name", "last_name", "groups_count", "students_count", "exams_count"]

    def get_queryset(self):
        from django.db.models import Count

        return User.objects.filter(role=Role.TEACHER).select_related("teacher_profile").annotate(
            groups_count=Count("teacher_profile__groups", distinct=True),
            students_count=Count("teacher_profile__groups__memberships__student", distinct=True),
            exams_count=Count("examinations", distinct=True),
        )

    def get_serializer_class(self):
        from .serializers import TeacherSerializer

        return TeacherSerializer


class UserViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdmin]
    serializer_class = UserSerializer
    queryset = User.objects.select_related("student_profile__current_level", "teacher_profile")
    filterset_fields = ["role", "is_active"]
    search_fields = ["first_name", "last_name", "username", "phone"]
    ordering_fields = ["first_name", "last_name", "date_joined", "role"]

    def destroy(self, request, *args, **kwargs):
        user = self.get_object()
        from apps.audit.services import record

        if user.pk == request.user.pk:
            raise DomainError("cannot_delete_self", status_code=400)
        label, role, pk_ = user.full_name, user.role, user.pk
        try:
            user.delete()
        except ProtectedError:
            raise DomainError("cannot_delete_has_records")
        record("user.deleted", target_type="user", target_label=label, detail={"id": pk_, "role": role})
        return Response(status=status.HTTP_204_NO_CONTENT)

    def perform_create(self, serializer):
        from apps.audit.services import record

        user = serializer.save()
        record("user.created", target=user, detail={"role": user.role, "username": user.username})

    def perform_update(self, serializer):
        from apps.audit.services import record

        before = {k: getattr(serializer.instance, k) for k in ("is_active", "username", "first_name", "last_name", "phone", "email")}
        user = serializer.save()
        changed = {k: [v, getattr(user, k)] for k, v in before.items() if getattr(user, k) != v}
        if "password" in serializer.validated_data:
            changed["password"] = ["***", "***"]
        if changed:
            record("user.updated", target=user, detail={"changed": changed})
        if before["is_active"] and not user.is_active:
            from .sessions import revoke

            revoke(user.login_sessions.all())

    @action(detail=True, methods=["post"], url_path="reset-password")
    def reset_password(self, request, pk=None):
        from apps.audit.services import record

        from .sessions import revoke

        user = self.get_object()
        password = generate_password()
        user.set_password(password)
        user.save(update_fields=["password"])
        revoke(user.login_sessions.all())
        record("user.password_reset", target=user)
        return Response({"username": user.username, "password": password})

    @action(detail=True, methods=["get"])
    def sessions(self, request, pk=None):
        from .sessions import active_sessions

        return Response(_session_rows(active_sessions(self.get_object())))

    @action(detail=True, methods=["post"], url_path="logout-all")
    def logout_all(self, request, pk=None):
        from apps.audit.services import record

        from .sessions import active_sessions, revoke

        user = self.get_object()
        n = revoke(active_sessions(user))
        record("session.revoked_all", target=user, detail={"count": n, "by_admin": True})
        return Response({"revoked": n})
