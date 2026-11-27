from rest_framework import serializers

from apps.accounts.models import Role
from apps.examinations.models import ExamKind
from apps.questions.models import QuestionType

from .models import ApprovalStatus, ExamResult


class ResultListSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.user.full_name", read_only=True)
    student_phone = serializers.CharField(source="student.user.phone", read_only=True)
    examination_title = serializers.CharField(source="examination.title", read_only=True)
    kind = serializers.CharField(source="examination.kind", read_only=True)
    level_code = serializers.CharField(source="level.code", read_only=True)
    target_level_code = serializers.CharField(source="examination.target_level.code", read_only=True, default=None)
    recommended_level_code = serializers.CharField(source="recommended_level.code", read_only=True, default=None)
    placed_level_code = serializers.CharField(source="placed_level.code", read_only=True, default=None)
    teacher_name = serializers.CharField(source="examination.created_by.full_name", read_only=True, default=None)
    started_at = serializers.DateTimeField(source="attempt.started_at", read_only=True)
    finished_at = serializers.DateTimeField(source="attempt.finished_at", read_only=True)
    attempt_status = serializers.CharField(source="attempt.status", read_only=True)

    class Meta:
        model = ExamResult
        fields = [
            "id", "student", "student_name", "student_phone", "examination", "examination_title", "kind",
            "level_code", "target_level_code", "total_score", "max_score", "percentage", "correct_count",
            "incorrect_count", "unanswered_count", "passed", "writing_pending", "recommendation", "recommended_level_code",
            "offer_status", "placed_level_code", "approval_status", "teacher_name", "started_at", "finished_at",
            "attempt_status", "created_at", "speaking_score", "speaking_max", "writing_score", "writing_max", "review_note",
        ]

    def to_representation(self, obj):
        data = super().to_representation(obj)
        request = self.context.get("request")
        if request is not None and request.user.role == Role.STUDENT:
            for key in SCORE_FIELDS:  # the student never sees points or right / wrong counts - only the outcome
                if key in data:
                    data[key] = None
            if awaiting_decision(obj):
                data["passed"] = None  # the teacher / admin has not decided yet: the student sees "result awaited"
        return data


SCORE_FIELDS = (
    "total_score", "max_score", "percentage", "correct_count", "incorrect_count", "unanswered_count",
    "speaking_score", "speaking_max", "section_scores", "passing_score", "speaking_points",
    "writing_score", "writing_max", "writing_points",
)


def awaiting_decision(result):
    """An upgrade result nobody has decided on yet (passed / not passed is the reviewer's call)."""
    return result.examination.kind == ExamKind.UPGRADE and (result.writing_pending or result.approval_status == ApprovalStatus.PENDING)


def _fmt_answer(question, options, answer):
    if not answer:
        return None
    qt = question.question_type
    by_id = {o.id: o for o in options}
    if qt in (QuestionType.FILL, QuestionType.WRITING):
        return answer.get("text") or None
    if qt == QuestionType.MATCH:
        pairs = answer.get("pairs") or {}
        return [{"left": o.text, "right": pairs.get(str(o.id), "")} for o in options]
    return [by_id[i].text for i in answer.get("option_ids", []) if i in by_id] or None


def _fmt_correct(question, options):
    qt = question.question_type
    if qt == QuestionType.WRITING:
        return []  # no answer key: a teacher scores it
    if qt == QuestionType.MATCH:
        return [{"left": o.text, "right": o.match_text} for o in options]
    return [o.text for o in options if o.is_correct]


class ResultDetailSerializer(ResultListSerializer):
    reviewed_by_name = serializers.CharField(source="reviewed_by.full_name", read_only=True, default=None)
    answers = serializers.SerializerMethodField()
    writing = serializers.SerializerMethodField()
    is_locked = serializers.BooleanField(read_only=True)
    passing_score = serializers.DecimalField(source="examination.passing_score", max_digits=7, decimal_places=2, read_only=True)
    speaking_points = serializers.DecimalField(source="examination.speaking_points", max_digits=7, decimal_places=2, read_only=True)
    speaking_by_name = serializers.CharField(source="speaking_by.full_name", read_only=True, default=None)
    writing_points = serializers.DecimalField(source="examination.writing_points", max_digits=7, decimal_places=2, read_only=True)
    writing_by_name = serializers.CharField(source="writing_by.full_name", read_only=True, default=None)

    class Meta(ResultListSerializer.Meta):
        fields = ResultListSerializer.Meta.fields + [
            "section_scores", "review_note", "reviewed_by_name", "reviewed_at", "is_locked", "answers", "writing", "passing_score",
            "speaking_points", "speaking_score", "speaking_max", "speaking_feedback", "speaking_by_name", "speaking_at",
            "writing_points", "writing_feedback", "writing_by_name", "writing_at",
        ]

    def get_writing(self, obj):
        """Written answers with the teacher's score and feedback (visible to the student too once scored)."""
        out = []
        saved = {a.question_id: a for a in obj.attempt.answers.all()}
        for vq in obj.attempt.variant.variant_questions.select_related("question").order_by("order"):
            q = vq.question
            if q.question_type != QuestionType.WRITING:
                continue
            a = saved.get(q.id)
            text = (a.answer.get("text") if a else "") or ""
            if self.context["request"].user.role == Role.STUDENT:
                continue  # no points for the student
            out.append({
                "question_id": q.id, "prompt": " ".join(x for x in (q.instruction, q.text) if x), "text": text, "max_points": float(q.points),
                "points": float(a.points_awarded) if a and not a.needs_review else None,
                "feedback": a.feedback if a else "", "needs_review": bool(a and a.needs_review),
                "words": len(text.split()),
            })
        return out

    def get_answers(self, obj):
        user = self.context["request"].user
        if user.role not in (Role.ADMIN, Role.TEACHER):
            return None  # the answer key / per-question review is for teachers and admins only - never the student
        saved = {a.question_id: a for a in obj.attempt.answers.all()}
        out = []
        for vq in obj.attempt.variant.variant_questions.select_related("question").prefetch_related("question__options"):
            q = vq.question
            options = list(q.options.all())
            a = saved.get(q.id)
            if q.question_type == QuestionType.WRITING:
                continue  # shown in the "writing" block with the teacher's score
            out.append({
                "question_id": q.id, "text": q.text, "type": q.question_type, "section": q.section,
                "points": float(q.points), "points_awarded": float(a.points_awarded) if a else 0.0,
                "is_correct": a.is_correct if a else None,
                "student_answer": _fmt_answer(q, options, a.answer if a else None),
                "correct_answer": _fmt_correct(q, options), "explanation": q.explanation,
            })
        return out
