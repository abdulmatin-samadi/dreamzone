from rest_framework import serializers

from .models import Group, Level


class LevelSerializer(serializers.ModelSerializer):
    student_count = serializers.SerializerMethodField()

    class Meta:
        model = Level
        fields = ["id", "code", "name", "description", "order", "is_active", "student_count"]

    def get_student_count(self, obj):
        return obj.students.count()

    def validate_code(self, value):
        return value.strip()


class GroupSerializer(serializers.ModelSerializer):
    level_code = serializers.CharField(source="level.code", read_only=True)
    teacher_name = serializers.CharField(source="teacher.user.full_name", read_only=True, default=None)
    student_count = serializers.IntegerField(source="memberships.count", read_only=True)

    class Meta:
        model = Group
        fields = ["id", "name", "level", "level_code", "teacher", "teacher_name", "schedule", "is_active", "student_count", "join_code"]
        read_only_fields = ["join_code"]

    def to_representation(self, obj):
        data = super().to_representation(obj)
        request = self.context.get("request")
        if request is None or getattr(request.user, "role", None) not in ("ADMIN", "TEACHER"):
            data.pop("join_code", None)  # only the admin and the teacher hand the code out (not students, not the front desk)
        return data
