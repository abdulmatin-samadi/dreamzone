from django.conf import settings
from django.contrib.auth import password_validation
from django.db import transaction
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import Role, TeacherProfile, User


def validate_language(value):
    if value not in dict(settings.SUPPORTED_LANGUAGES):
        raise serializers.ValidationError("Unsupported language.")
    return value


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    password = serializers.CharField(write_only=True, required=False, style={"input_type": "password"})
    student_id = serializers.SerializerMethodField()
    teacher_id = serializers.SerializerMethodField()
    current_level = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "username", "first_name", "last_name", "full_name", "email", "phone", "role", "language",
            "is_active", "password", "student_id", "teacher_id", "current_level", "date_joined",
        ]
        read_only_fields = ["date_joined"]

    def get_student_id(self, obj):
        p = getattr(obj, "student_profile", None) if obj.role == Role.STUDENT else None
        return p.id if p else None

    def get_teacher_id(self, obj):
        p = getattr(obj, "teacher_profile", None) if obj.role == Role.TEACHER else None
        return p.id if p else None

    def get_current_level(self, obj):
        p = getattr(obj, "student_profile", None) if obj.role == Role.STUDENT else None
        return p.current_level.code if p and p.current_level else None

    def validate_language(self, value):
        return validate_language(value)

    def validate(self, attrs):
        password = attrs.get("password")
        if password:
            password_validation.validate_password(password, self.instance)
        elif self.instance is None:
            raise serializers.ValidationError({"password": "This field is required."})
        if self.instance is not None and "role" in attrs and attrs["role"] != self.instance.role:
            raise serializers.ValidationError({"role": "Role cannot be changed after creation."})
        return attrs

    @transaction.atomic
    def create(self, validated):
        password = validated.pop("password")
        user = User(**validated)
        user.set_password(password)
        user.save()
        if user.role == Role.TEACHER:
            TeacherProfile.objects.create(user=user)
        elif user.role == Role.STUDENT:
            from apps.students.models import StudentProfile

            StudentProfile.objects.create(user=user, registered_by=self.context["request"].user)
        return user

    def update(self, instance, validated):
        password = validated.pop("password", None)
        for k, v in validated.items():
            setattr(instance, k, v)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class TeacherSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    teacher_id = serializers.IntegerField(source="teacher_profile.id", read_only=True)
    groups_count = serializers.IntegerField(read_only=True)
    students_count = serializers.IntegerField(read_only=True)
    exams_count = serializers.IntegerField(read_only=True)
    groups = serializers.SerializerMethodField()
    exams = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "teacher_id", "username", "first_name", "last_name", "full_name", "phone", "email", "is_active",
                  "language", "groups_count", "students_count", "exams_count", "groups", "exams", "date_joined"]

    def get_groups(self, obj):
        return [{"id": g.id, "name": g.name, "level": g.level.code, "students": g.memberships.count()}
                for g in obj.teacher_profile.groups.select_related("level")]

    def get_exams(self, obj):
        return [{"id": e.id, "title": e.title, "status": e.status, "level": e.level.code,
                 "target": e.target_level.code if e.target_level else None}
                for e in obj.examinations.select_related("level", "target_level")[:20]]


class MeSerializer(serializers.ModelSerializer):
    """What a user may change about themselves."""

    full_name = serializers.CharField(read_only=True)
    current_level = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "full_name", "email", "phone", "role", "language",
                  "current_level"]
        read_only_fields = ["id", "username", "role"]

    def get_current_level(self, obj):
        p = getattr(obj, "student_profile", None) if obj.role == Role.STUDENT else None
        return p.current_level.code if p and p.current_level else None

    def validate_language(self, value):
        return validate_language(value)


class LoginSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        from django.contrib.auth.models import update_last_login
        from rest_framework_simplejwt.serializers import TokenObtainSerializer

        from .sessions import start_session

        TokenObtainSerializer.validate(self, attrs)  # authenticates, sets self.user
        refresh, _session = start_session(self.user, self.context.get("request"))
        update_last_login(None, self.user)
        return {"refresh": str(refresh), "access": str(refresh.access_token), "user": MeSerializer(self.user).data}


class ChangeUsernameSerializer(serializers.Serializer):
    """A user changes their own login. The current password proves it is really them."""

    password = serializers.CharField(write_only=True)
    username = serializers.CharField(min_length=3, max_length=150)

    def validate_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("Wrong password.")
        return value

    def validate_username(self, value):
        from django.contrib.auth.validators import UnicodeUsernameValidator

        value = value.strip()
        UnicodeUsernameValidator()(value)  # letters, digits and @ . + - _ only
        user = self.context["request"].user
        if User.objects.filter(username__iexact=value).exclude(pk=user.pk).exists():
            raise serializers.ValidationError("This login is already taken.")
        return value


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    def validate_old_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("Wrong password.")
        return value

    def validate_new_password(self, value):
        password_validation.validate_password(value, self.context["request"].user)
        return value
