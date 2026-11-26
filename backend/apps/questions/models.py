from django.conf import settings
from django.db import models


class QuestionType(models.TextChoices):
    MULTIPLE_CHOICE = "MCQ", "Multiple choice"
    MULTIPLE_SELECT = "MSQ", "Multiple select"
    TRUE_FALSE = "TF", "True / False"
    FILL = "FILL", "Fill in the blanks"
    MATCH = "MATCH", "Matching"
    READING = "READING", "Reading comprehension"
    LISTENING = "LISTENING", "Listening comprehension"
    WRITING = "WRITING", "Writing (checked by the teacher)"


class Section(models.TextChoices):
    GRAMMAR = "GRAMMAR", "Grammar"
    VOCABULARY = "VOCABULARY", "Vocabulary"
    READING = "READING", "Reading"
    LISTENING = "LISTENING", "Listening"
    WRITING = "WRITING", "Writing"


class Passage(models.Model):
    """Shared reading text (and/or audio track) referenced by several questions."""

    title = models.CharField(max_length=200)
    text = models.TextField(blank=True)
    audio = models.FileField(upload_to="passages/audio/", blank=True, null=True)
    level = models.ForeignKey("academics.Level", on_delete=models.PROTECT, related_name="passages")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class Category(models.TextChoices):
    """How the exercise is presented to teachers (the grading type is ``question_type``)."""

    GAP = "GAP", "Gap filling"
    MCQ = "MCQ", "Multiple choice"
    TICK = "TICK", "Tick the correct sentence"
    MISTAKE = "MISTAKE", "Find the mistake"
    ODD = "ODD", "Odd one out"
    WORDFORM = "WORDFORM", "Word formation (past simple)"
    DIALOGUE = "DIALOGUE", "Dialogue completion"
    TFREAD = "TFREAD", "Reading - True/False"
    GAPTEXT = "GAPTEXT", "Gaps in a text"
    READQA = "READQA", "Reading - answer the questions"
    LISTEN = "LISTEN", "Listening"
    WRITING = "WRITING", "Writing"


class Question(models.Model):
    text = models.TextField()
    question_type = models.CharField(max_length=10, choices=QuestionType.choices)
    section = models.CharField(max_length=12, choices=Section.choices, db_index=True)
    instruction = models.CharField(max_length=300, blank=True, help_text="Heading of the exercise, shown once above a group of questions.")
    gap_no = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Number of the blank [[n]] in the passage (gaps in a text).")
    category = models.CharField(max_length=10, choices=Category.choices, blank=True, db_index=True)
    level = models.ForeignKey("academics.Level", on_delete=models.PROTECT, related_name="questions")
    points = models.DecimalField(max_digits=6, decimal_places=2, default=1)
    explanation = models.TextField(blank=True)
    image = models.ImageField(upload_to="questions/images/", blank=True, null=True)
    audio = models.FileField(upload_to="questions/audio/", blank=True, null=True)
    reading_passage = models.TextField(blank=True, help_text="Inline passage (for a shared one use `passage`).")
    passage = models.ForeignKey(Passage, on_delete=models.SET_NULL, null=True, blank=True, related_name="questions")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="questions")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["level", "section", "question_type"])]
        constraints = [models.CheckConstraint(condition=models.Q(points__gt=0), name="question_points_positive")]

    def __str__(self):
        return f"[{self.question_type}] {self.text[:60]}"


class AnswerOption(models.Model):
    """Answer option.

    * choice types: ``text`` + ``is_correct``
    * FILL: every option is an accepted answer (``is_correct=True``)
    * MATCH: ``text`` is the left item and ``match_text`` its correct partner
    """

    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="options")
    text = models.CharField(max_length=500)
    match_text = models.CharField(max_length=500, blank=True)
    is_correct = models.BooleanField(default=False)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]
        indexes = [models.Index(fields=["question", "order"])]

