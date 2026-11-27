from django.conf import settings
from django.utils import timezone
from rest_framework import serializers

from apps.accounts.models import Role, User
from apps.questions.models import Question, QuestionType

from .models import (
    AttemptStatus, ExamAssignment, ExamKind, Examination, ExaminationVariant, StudentAnswer,
    VariantQuestion,
)
from .services import seconds_remaining


class ExaminationSerializer(serializers.ModelSerializer):
    level_code = serializers.CharField(source="level.code", read_only=True)
    target_level_code = serializers.CharField(source="target_level.code", read_only=True, default=None)
    created_by_name = serializers.CharField(source="created_by.full_name", read_only=True, default=None)
    variant_count = serializers.SerializerMethodField()
    assignment_count = serializers.SerializerMethodField()
    attempt_count = serializers.SerializerMethodField()
    locked = serializers.SerializerMethodField()
    teachers = serializers.PrimaryKeyRelatedField(many=True, required=False, queryset=User.objects.filter(role=Role.TEACHER))
    teacher_names = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()

    class Meta:
        model = Examination
        fields = [
            "id", "kind", "title", "level", "level_code", "target_level", "target_level_code", "instructions",
            "duration_minutes", "passing_score", "high_threshold", "speaking_points", "writing_points", "status", "shuffle_questions", "shuffle_options",
            "show_correct_answers", "teachers", "teacher_names", "created_by_name", "variant_count", "assignment_count", "attempt_count",
            "locked", "can_edit", "created_at",
        ]
        read_only_fields = ["status"]

    def get_variant_count(self, obj):
        return obj.variants.count()

    def get_assignment_count(self, obj):
        return obj.assignments.count()

    def get_attempt_count(self, obj):
        return obj.attempts.count()

    def get_teacher_names(self, obj):
        return [t.full_name for t in obj.teachers.all()]

    def get_locked(self, obj):
        return obj.attempts.exists()

    def get_can_edit(self, obj):
        """False for a teacher who only got the exam through a group: they assign it, they don't change it."""
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user is None or user.role == Role.ADMIN:
            return True
        return obj.created_by_id == user.id or obj.teachers.filter(pk=user.pk).exists()

    def validate(self, attrs):
        inst = self.instance
        get = lambda k: attrs.get(k, getattr(inst, k, None))
        user = self.context["request"].user
        if "teachers" in attrs and user.role != Role.ADMIN:
            raise serializers.ValidationError({"teachers": "Only administrators choose the teachers."})
        kind, level, target = get("kind"), get("level"), get("target_level")
        if kind == ExamKind.PLACEMENT:
            if user.role != Role.ADMIN:
                raise serializers.ValidationError({"kind": "Only administrators manage placement tests."})
            attrs["target_level"] = None
            clash = Examination.objects.filter(kind=ExamKind.PLACEMENT, level=level)
            if inst:
                clash = clash.exclude(pk=inst.pk)
            if clash.exists():
                raise serializers.ValidationError({"level": "A placement test for this level already exists."})
        else:
            if target is None:
                raise serializers.ValidationError({"target_level": "Target level is required."})
            if target.order <= level.order:
                raise serializers.ValidationError({"target_level": "Target level must be higher than the current level."})
            attrs["high_threshold"] = None
        high, passing = get("high_threshold"), get("passing_score")
        if kind == ExamKind.PLACEMENT and high is not None and passing is not None and high < passing:
            raise serializers.ValidationError({"high_threshold": "Must be greater than or equal to the passing score."})
        if inst and inst.attempts.exists():
            for field in ("kind", "level", "target_level"):
                if field in attrs and attrs[field] != getattr(inst, field):
                    raise serializers.ValidationError({field: "Cannot be changed after students have taken the exam."})
        return attrs


class VariantQuestionSerializer(serializers.ModelSerializer):
    text = serializers.CharField(source="question.text", read_only=True)
    question_type = serializers.CharField(source="question.question_type", read_only=True)
    section = serializers.CharField(source="question.section", read_only=True)
    points = serializers.DecimalField(source="question.points", max_digits=6, decimal_places=2, read_only=True)

    class Meta:
        model = VariantQuestion
        fields = ["id", "question", "order", "text", "question_type", "section", "points"]


class VariantSerializer(serializers.ModelSerializer):
    question_count = serializers.IntegerField(source="variant_questions.count", read_only=True)
    total_points = serializers.SerializerMethodField()
    questions = VariantQuestionSerializer(source="variant_questions", many=True, read_only=True)

    class Meta:
        model = ExaminationVariant
        fields = ["id", "examination", "name", "order", "question_count", "total_points", "questions"]

    def get_total_points(self, obj):
        return float(sum(vq.question.points for vq in obj.variant_questions.all()))

    def validate_examination(self, value):
        user = self.context["request"].user
        if user.role != Role.ADMIN and value.created_by_id != user.id:
            raise serializers.ValidationError("Not your examination.")
        return value


class ExamAssignmentSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.user.full_name", read_only=True)
    student_is_guest = serializers.BooleanField(source="student.is_guest", read_only=True)
    examination_title = serializers.CharField(source="examination.title", read_only=True)
    examination_kind = serializers.CharField(source="examination.kind", read_only=True)
    level_code = serializers.CharField(source="examination.level.code", read_only=True)
    target_level_code = serializers.CharField(source="examination.target_level.code", read_only=True, default=None)
    variant_name = serializers.CharField(source="variant.name", read_only=True)
    group_name = serializers.CharField(source="group.name", read_only=True, default=None)
    state = serializers.SerializerMethodField()
    attempt_id = serializers.SerializerMethodField()
    result_id = serializers.SerializerMethodField()

    class Meta:
        model = ExamAssignment
        fields = [
            "id", "examination", "examination_title", "examination_kind", "level_code", "target_level_code",
            "student", "student_name", "student_is_guest", "variant", "variant_name", "group", "group_name", "available_from",
            "available_until", "state", "attempt_id", "result_id", "created_at",
        ]
        read_only_fields = ["examination", "student", "group"]

    def _attempt(self, obj):
        return getattr(obj, "attempt", None) if hasattr(obj, "attempt") else None

    def get_state(self, obj):
        return assignment_state(obj)

    def get_attempt_id(self, obj):
        a = self._attempt(obj)
        return a.id if a else None

    def get_result_id(self, obj):
        a = self._attempt(obj)
        return a.result.id if a is not None and hasattr(a, "result") else None

    def validate(self, attrs):
        inst = self.instance
        if inst is not None:
            if hasattr(inst, "attempt"):
                raise serializers.ValidationError("The student already started this examination.")
            variant = attrs.get("variant")
            if variant and variant.examination_id != inst.examination_id:
                raise serializers.ValidationError({"variant": "Variant belongs to another examination."})
        start = attrs.get("available_from", getattr(inst, "available_from", None))
        end = attrs.get("available_until", getattr(inst, "available_until", None))
        if start and end and end <= start:
            raise serializers.ValidationError({"available_until": "Must be after the start."})
        return attrs


def assignment_state(a, now=None):
    now = now or timezone.now()
    attempt = getattr(a, "attempt", None) if hasattr(a, "attempt") else None
    if attempt is not None:
        if attempt.status == AttemptStatus.PENDING_TEACHER_APPROVAL:
            return "pending_approval"
        return "in_progress" if attempt.status == AttemptStatus.IN_PROGRESS and now < attempt.deadline_at else "completed"
    if a.available_from and now < a.available_from:
        return "scheduled"
    if a.available_until and now > a.available_until:
        return "expired"
    return "available"


class MyAssignmentSerializer(ExamAssignmentSerializer):
    """Student view of an assignment – no staff-only information."""

    duration_minutes = serializers.IntegerField(source="examination.duration_minutes", read_only=True)
    instructions = serializers.CharField(source="examination.instructions", read_only=True)
    question_count = serializers.SerializerMethodField()
    passing_score = serializers.DecimalField(source="examination.passing_score", max_digits=5, decimal_places=2, read_only=True)

    class Meta(ExamAssignmentSerializer.Meta):
        fields = [
            "id", "examination_title", "examination_kind", "level_code", "target_level_code", "available_from",
            "available_until", "state", "attempt_id", "result_id", "duration_minutes", "instructions",
            "question_count", "max_points", "passing_points", "passing_score", "created_at",
        ]

    max_points = serializers.SerializerMethodField()
    passing_points = serializers.SerializerMethodField()

    def get_question_count(self, obj):
        return obj.variant.variant_questions.count()

    def get_max_points(self, obj):
        exam = obj.examination  # + the speaking / paper-writing parts the teacher scores by hand
        return float(sum(vq.question.points for vq in obj.variant.variant_questions.select_related("question"))
                     + exam.speaking_points + exam.writing_points)

    def get_passing_points(self, obj):
        return float(obj.examination.passing_score)  # thresholds are kept in points


# --------------------------------------------------------------------------- exam taking payload
def _file_url(request, f):
    return request.build_absolute_uri(f.url) if f else None


def build_attempt_payload(attempt, request):
    """Everything the student needs to sit the exam – and never the correct answers."""
    exam = attempt.examination
    layout = attempt.layout
    questions = {
        q.id: q for q in Question.objects.filter(id__in=layout["questions"])
        .select_related("passage").prefetch_related("options")
    }
    saved = {a.question_id: a.answer for a in StudentAnswer.objects.filter(attempt=attempt)}
    items = []
    for qid in ([] if attempt.is_pending_approval else layout["questions"]):
        q = questions[qid]
        opts = {o.id: o for o in q.options.all()}
        entry = {
            "id": q.id, "type": q.question_type, "section": q.section, "category": q.category, "instruction": q.instruction, "gap_no": q.gap_no, "text": q.text, "points": float(q.points),
            "image": _file_url(request, q.image),
            "audio": _file_url(request, q.audio or (q.passage.audio if q.passage and q.passage.audio else None)),
            "passage": (
                {"id": q.passage.id, "title": q.passage.title, "text": q.passage.text, "audio": _file_url(request, q.passage.audio)}
                if q.passage else ({"id": None, "title": "", "text": q.reading_passage, "audio": None} if q.reading_passage else None)
            ),
            "answer": saved.get(qid),
        }
        if q.question_type == QuestionType.FILL:
            entry["options"] = []
        else:
            entry["options"] = [{"id": oid, "text": opts[oid].text} for oid in layout["options"].get(str(qid), []) if oid in opts]
        if q.question_type == QuestionType.MATCH:
            entry["choices"] = layout.get("matches", {}).get(str(qid), [])
        items.append(entry)
    return {
        "id": attempt.id, "examination": exam.title, "kind": exam.kind, "level": exam.level.code,
        "target_level": exam.target_level.code if exam.target_level else None,
        "status": attempt.status, "started_at": attempt.started_at, "deadline_at": attempt.deadline_at,
        "server_now": timezone.now(), "remaining_seconds": seconds_remaining(attempt),
        "duration_minutes": exam.duration_minutes, "questions": items,
        "result_id": attempt.result.id if attempt.is_finished and hasattr(attempt, "result") else None,
        "violation_seconds_left": (
            max(0, int((attempt.violation_deadline_at - timezone.now()).total_seconds()))
            if attempt.violation_deadline_at else None
        ),
        "violation_limit_seconds": getattr(settings, "FULLSCREEN_VIOLATION_SECONDS", 10),
    }


class AnswerItemSerializer(serializers.Serializer):
    question_id = serializers.IntegerField()
    answer = serializers.DictField()


class AnswersPayloadSerializer(serializers.Serializer):
    answers = AnswerItemSerializer(many=True, allow_empty=False, max_length=500)


class AssignSerializer(serializers.Serializer):
    student_ids = serializers.ListField(child=serializers.IntegerField(), required=False, default=list)
    group_ids = serializers.ListField(child=serializers.IntegerField(), required=False, default=list)
    variant = serializers.PrimaryKeyRelatedField(queryset=ExaminationVariant.objects.all(), required=False, allow_null=True)
    available_from = serializers.DateTimeField(required=False, allow_null=True)
    available_until = serializers.DateTimeField(required=False, allow_null=True)

    def validate(self, attrs):
        if not attrs["student_ids"] and not attrs["group_ids"]:
            raise serializers.ValidationError("Select at least one student or group.")
        if attrs.get("available_from") and attrs.get("available_until") and attrs["available_until"] <= attrs["available_from"]:
            raise serializers.ValidationError({"available_until": "Must be after the start."})
        return attrs
