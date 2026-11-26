from rest_framework import serializers

from apps.academics.models import Group, Level

from .models import LevelChangeHistory, StudentProfile


class StudentSerializer(serializers.ModelSerializer):
    first_name = serializers.CharField(source="user.first_name")
    last_name = serializers.CharField(source="user.last_name")
    phone = serializers.CharField(source="user.phone")
    username = serializers.CharField(source="user.username", read_only=True)
    is_active = serializers.BooleanField(source="user.is_active", read_only=True)
    full_name = serializers.CharField(source="user.full_name", read_only=True)
    current_level_code = serializers.CharField(source="current_level.code", read_only=True, default=None)
    initial_level_code = serializers.CharField(source="initial_level.code", read_only=True, default=None)
    groups = serializers.SerializerMethodField()

    class Meta:
        model = StudentProfile
        fields = [
            "id", "first_name", "last_name", "full_name", "phone", "username", "is_active", "is_guest", "current_level",
            "current_level_code", "initial_level", "initial_level_code", "notes", "groups", "created_at",
        ]
        read_only_fields = ["current_level", "created_at", "is_guest"]

    def get_groups(self, obj):
        return [{"id": g.id, "name": g.name} for g in obj.groups.all()]

    def validate_phone(self, value):
        value = value.strip()
        if len(value) < 7:
            raise serializers.ValidationError("Enter a valid phone number.")
        return value

    def update(self, instance, validated):
        user_data = validated.pop("user", {})
        for k, v in user_data.items():
            setattr(instance.user, k, v)
        if user_data:
            instance.user.save()
        return super().update(instance, validated)


class StudentRegisterSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    phone = serializers.CharField(max_length=20, min_length=7)
    initial_level = serializers.PrimaryKeyRelatedField(queryset=Level.objects.filter(is_active=True))
    group = serializers.PrimaryKeyRelatedField(queryset=Group.objects.filter(is_active=True), required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True)


class LevelChangeSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.user.full_name", read_only=True)
    from_level_code = serializers.CharField(source="from_level.code", read_only=True, default=None)
    to_level_code = serializers.CharField(source="to_level.code", read_only=True)
    changed_by_name = serializers.CharField(source="changed_by.full_name", read_only=True, default=None)

    class Meta:
        model = LevelChangeHistory
        fields = ["id", "student", "student_name", "from_level_code", "to_level_code", "reason", "result",
                  "changed_by_name", "note", "created_at"]
