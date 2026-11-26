import json

from django.db import transaction
from rest_framework import serializers

from apps.core.exceptions import DomainError

from .models import AnswerOption, Passage, Question, QuestionType

CHOICE_SINGLE = {QuestionType.MULTIPLE_CHOICE, QuestionType.READING, QuestionType.LISTENING}


class AnswerOptionSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)

    class Meta:
        model = AnswerOption
        fields = ["id", "text", "match_text", "is_correct", "order"]


class PassageSerializer(serializers.ModelSerializer):
    level_code = serializers.CharField(source="level.code", read_only=True)
    question_count = serializers.IntegerField(source="questions.count", read_only=True)

    class Meta:
        model = Passage
        fields = ["id", "title", "text", "audio", "level", "level_code", "question_count", "created_at"]
        extra_kwargs = {"audio": {"required": False, "allow_null": True}}

    def validate(self, attrs):
        text = attrs.get("text", getattr(self.instance, "text", ""))
        audio = attrs.get("audio", getattr(self.instance, "audio", None))
        if not text and not audio:
            raise serializers.ValidationError("A passage needs text or an audio file.")
        return attrs


class QuestionSerializer(serializers.ModelSerializer):
    """Staff-facing serializer (includes correct answers)."""

    options = AnswerOptionSerializer(many=True, required=False)
    level_code = serializers.CharField(source="level.code", read_only=True)
    passage_title = serializers.CharField(source="passage.title", read_only=True, default=None)
    created_by_name = serializers.CharField(source="created_by.full_name", read_only=True, default=None)
    in_use = serializers.SerializerMethodField()

    class Meta:
        model = Question
        fields = [
            "id", "text", "question_type", "section", "category", "instruction", "gap_no", "level", "level_code", "points", "explanation", "image",
            "audio", "reading_passage", "passage", "passage_title", "options", "is_active", "created_by_name",
            "in_use", "created_at",
        ]
        extra_kwargs = {
            "image": {"required": False, "allow_null": True},
            "audio": {"required": False, "allow_null": True},
            "passage": {"required": False, "allow_null": True},
        }

    def get_in_use(self, obj):
        return obj.variant_links.exists()

    # multipart helper: options arrive as a JSON string
    def to_internal_value(self, data):
        if hasattr(data, "getlist"):
            data = {k: data.get(k) for k in data.keys()}
            for key in ("passage", "image", "audio"):
                if data.get(key) == "":
                    data[key] = None
        if isinstance(data.get("options"), str):
            try:
                data["options"] = json.loads(data["options"])
            except ValueError:
                raise serializers.ValidationError({"options": "Invalid JSON."})
        return super().to_internal_value(data)

    def validate(self, attrs):
        inst = self.instance
        get = lambda k, default=None: attrs.get(k, getattr(inst, k, default))
        qtype, options = get("question_type"), attrs.get("options")
        if options is None:
            options = [] if inst is None else list(inst.options.values("text", "match_text", "is_correct"))
        correct = [o for o in options if o.get("is_correct")]

        if qtype in CHOICE_SINGLE:
            if len(options) < 2 or len(correct) != 1:
                raise serializers.ValidationError({"options": "Provide at least 2 options with exactly 1 correct."})
        elif qtype == QuestionType.MULTIPLE_SELECT:
            if len(options) < 2 or len(correct) < 1:
                raise serializers.ValidationError({"options": "Provide at least 2 options and 1+ correct answers."})
        elif qtype == QuestionType.TRUE_FALSE:
            if len(options) != 2 or len(correct) != 1:
                raise serializers.ValidationError({"options": "True/False needs 2 options with exactly 1 correct."})
        elif qtype == QuestionType.FILL:
            if len(options) < 1:
                raise serializers.ValidationError({"options": "Provide at least one accepted answer."})
        elif qtype == QuestionType.MATCH:
            if len(options) < 2 or any(not o.get("text") or not o.get("match_text") for o in options):
                raise serializers.ValidationError({"options": "Provide 2+ complete matching pairs."})

        if qtype == QuestionType.READING and not (get("reading_passage") or get("passage")):
            raise serializers.ValidationError({"passage": "Reading questions need a passage."})
        if qtype == QuestionType.LISTENING:
            passage = get("passage")
            if not (get("audio") or (passage and passage.audio)):
                raise serializers.ValidationError({"audio": "Listening questions need an audio file."})
        return attrs

    def _write_options(self, question, options):
        qtype = question.question_type
        question.options.all().delete()
        AnswerOption.objects.bulk_create([
            AnswerOption(
                question=question, text=o["text"], order=o.get("order", i),
                match_text=o.get("match_text", "") if qtype == QuestionType.MATCH else "",
                is_correct=True if qtype == QuestionType.FILL else (False if qtype == QuestionType.MATCH else o.get("is_correct", False)),
            )
            for i, o in enumerate(options)
        ])

    @transaction.atomic
    def create(self, validated):
        options = validated.pop("options", [])
        question = Question.objects.create(created_by=self.context["request"].user, **validated)
        self._write_options(question, options)
        return question

    @transaction.atomic
    def update(self, instance, validated):
        options = validated.pop("options", None)
        locked = instance.variant_links.filter(variant__examination__attempts__isnull=False).exists()
        if locked and (options is not None or "points" in validated or "question_type" in validated):
            raise DomainError("question_in_use")
        instance = super().update(instance, validated)
        if options is not None:
            self._write_options(instance, options)
        return instance
