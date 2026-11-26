from django.conf import settings
from django.db import models
from django.db.models import Q


class ExamKind(models.TextChoices):
    PLACEMENT = "PLACEMENT", "Placement test"
    UPGRADE = "UPGRADE", "Level upgrade examination"


class ExamStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft / inactive"
    PUBLISHED = "PUBLISHED", "Published / active"


class Examination(models.Model):
    kind = models.CharField(max_length=10, choices=ExamKind.choices, db_index=True)
    title = models.CharField(max_length=200)
    level = models.ForeignKey(
        "academics.Level", on_delete=models.PROTECT, related_name="examinations",
        help_text="Placement: the level being tested. Upgrade: the student's current level.",
    )
    target_level = models.ForeignKey(
        "academics.Level", on_delete=models.PROTECT, null=True, blank=True, related_name="target_examinations"
    )
    instructions = models.TextField(blank=True)
    duration_minutes = models.PositiveIntegerField(default=60)
    passing_score = models.DecimalField(
        max_digits=7, decimal_places=2, default=60,
        help_text="Points. Upgrade: the pass mark. Placement: below this the previous level is offered.",
    )
    high_threshold = models.DecimalField(
        max_digits=7, decimal_places=2, null=True, blank=True,
        help_text="Placement only, points. At/above this score the next level is offered.",
    )
    status = models.CharField(max_length=10, choices=ExamStatus.choices, default=ExamStatus.DRAFT, db_index=True)
    shuffle_questions = models.BooleanField(default=True, help_text="Each student gets the questions of every exercise in a different order.")
    shuffle_options = models.BooleanField(default=True, help_text="Each student gets the answer options in a different order.")
    speaking_points = models.DecimalField(
        max_digits=7, decimal_places=2, default=0,
        help_text="Upgrade: points of the oral (speaking) part, scored by the teacher / admin. 0 = no speaking.")
    show_correct_answers = models.BooleanField(
        default=False, help_text="Let students see correct answers & explanations after submitting."
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="examinations")
    teachers = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name="shared_exams",
        help_text="Teachers (besides the creator) who see this examination, assign it and review its results.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["level"], condition=Q(kind="PLACEMENT"), name="uniq_placement_exam_per_level"
            ),
            models.CheckConstraint(
                condition=Q(kind="PLACEMENT") | Q(target_level__isnull=False), name="upgrade_requires_target_level"
            ),
            models.CheckConstraint(
                condition=Q(passing_score__gte=0), name="exam_passing_points_nonneg"
            ),
            models.CheckConstraint(
                condition=Q(high_threshold__isnull=True) | Q(high_threshold__gte=0),
                name="exam_high_points_nonneg",
            ),
            models.CheckConstraint(condition=Q(duration_minutes__gt=0), name="exam_duration_positive"),
        ]

    def __str__(self):
        return self.title

    @property
    def is_published(self):
        return self.status == ExamStatus.PUBLISHED


class ExaminationVariant(models.Model):
    examination = models.ForeignKey(Examination, on_delete=models.CASCADE, related_name="variants")
    name = models.CharField(max_length=50)
    order = models.PositiveSmallIntegerField(default=0)
    questions = models.ManyToManyField("questions.Question", through="VariantQuestion", related_name="variants")

    class Meta:
        ordering = ["order", "name"]
        constraints = [models.UniqueConstraint(fields=["examination", "name"], name="uniq_variant_name_per_exam")]

    def __str__(self):
        return f"{self.examination.title} / {self.name}"


class VariantQuestion(models.Model):
    variant = models.ForeignKey(ExaminationVariant, on_delete=models.CASCADE, related_name="variant_questions")
    question = models.ForeignKey("questions.Question", on_delete=models.PROTECT, related_name="variant_links")
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]
        constraints = [models.UniqueConstraint(fields=["variant", "question"], name="uniq_question_per_variant")]


class GroupExam(models.Model):
    """The admin gives an upgrade exam to a group. Nobody sits it yet: the group's teacher then
    chooses which of the group's students get it (and when) - see ``ExamAssignment``."""

    examination = models.ForeignKey(Examination, on_delete=models.CASCADE, related_name="group_grants")
    group = models.ForeignKey("academics.Group", on_delete=models.CASCADE, related_name="exam_grants")
    assigned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["examination", "group"], name="uniq_exam_per_group")]


class ExamAssignment(models.Model):
    """A student is entitled to sit an examination exactly once."""

    examination = models.ForeignKey(Examination, on_delete=models.CASCADE, related_name="assignments")
    student = models.ForeignKey("students.StudentProfile", on_delete=models.CASCADE, related_name="assignments")
    variant = models.ForeignKey(ExaminationVariant, on_delete=models.PROTECT, related_name="assignments")
    group = models.ForeignKey("academics.Group", on_delete=models.SET_NULL, null=True, blank=True, related_name="assignments")
    assigned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    origin_result = models.ForeignKey(
        "results.ExamResult", on_delete=models.SET_NULL, null=True, blank=True, related_name="follow_up_assignments",
        help_text="Placement result whose recommendation produced this assignment.",
    )
    available_from = models.DateTimeField(null=True, blank=True)
    available_until = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["examination", "student"], name="uniq_assignment_exam_student"),
            models.CheckConstraint(
                condition=Q(available_until__isnull=True) | Q(available_from__isnull=True)
                | Q(available_until__gt=models.F("available_from")),
                name="assignment_window_valid",
            ),
        ]
        indexes = [models.Index(fields=["student", "-created_at"])]


class AttemptStatus(models.TextChoices):
    IN_PROGRESS = "IN_PROGRESS", "In progress"
    SUBMITTED = "SUBMITTED", "Submitted"
    AUTO_SUBMITTED = "AUTO_SUBMITTED", "Auto-submitted (time expired)"
    # Fullscreen rule broken: answers are saved, the clock is frozen, a teacher decides.
    PENDING_TEACHER_APPROVAL = "PENDING_TEACHER_APPROVAL", "Pending teacher approval"


class ExamAttempt(models.Model):
    # OneToOne => a database-level guarantee of a single attempt per assignment.
    assignment = models.OneToOneField(ExamAssignment, on_delete=models.PROTECT, related_name="attempt")
    student = models.ForeignKey("students.StudentProfile", on_delete=models.CASCADE, related_name="attempts")
    examination = models.ForeignKey(Examination, on_delete=models.PROTECT, related_name="attempts")
    variant = models.ForeignKey(ExaminationVariant, on_delete=models.PROTECT, related_name="attempts")
    status = models.CharField(max_length=32, choices=AttemptStatus.choices, default=AttemptStatus.IN_PROGRESS, db_index=True)
    started_at = models.DateTimeField()
    deadline_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)
    started_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    layout = models.JSONField(default=dict, help_text="Frozen question / option order for this attempt.")
    # Fullscreen enforcement (all decisions are made on the server)
    violation_deadline_at = models.DateTimeField(null=True, blank=True)
    terminated_at = models.DateTimeField(null=True, blank=True)
    paused_remaining_seconds = models.PositiveIntegerField(null=True, blank=True)
    resume_count = models.PositiveSmallIntegerField(default=0)
    # One device per test: the browser that opened it (its random localStorage id) owns it until staff release it.
    device_id = models.CharField(max_length=64, blank=True)
    device_label = models.CharField(max_length=160, blank=True, help_text="Computer name + browser, for the live list.")
    last_seen_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["status", "deadline_at"]),
            models.Index(fields=["student", "-started_at"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["examination", "student"], name="uniq_attempt_exam_student"),
        ]

    @property
    def is_finished(self):
        return self.status in (AttemptStatus.SUBMITTED, AttemptStatus.AUTO_SUBMITTED)

    @property
    def is_pending_approval(self):
        return self.status == AttemptStatus.PENDING_TEACHER_APPROVAL


class ViolationKind(models.TextChoices):
    FULLSCREEN_EXIT = "FULLSCREEN_EXIT", "Left fullscreen"
    TAB_HIDDEN = "TAB_HIDDEN", "Left the test page"
    NOT_SUPPORTED = "NOT_SUPPORTED", "Fullscreen unavailable"
    TERMINATED = "TERMINATED", "Test terminated (10 s expired)"
    RETURNED = "RETURNED", "Returned in time"
    RESUMED = "RESUMED", "Resumed by staff"
    OTHER_DEVICE = "OTHER_DEVICE", "Opened on another device (refused)"
    DEVICE_RELEASED = "DEVICE_RELEASED", "Device released by staff"
    FINALIZED = "FINALIZED", "Finalised by staff"


class AttemptViolation(models.Model):
    attempt = models.ForeignKey(ExamAttempt, on_delete=models.CASCADE, related_name="violations")
    kind = models.CharField(max_length=20, choices=ViolationKind.choices)
    detail = models.CharField(max_length=200, blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


class StudentAnswer(models.Model):
    attempt = models.ForeignKey(ExamAttempt, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey("questions.Question", on_delete=models.PROTECT, related_name="student_answers")
    answer = models.JSONField(default=dict)
    is_correct = models.BooleanField(null=True)
    points_awarded = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    answered_at = models.DateTimeField(auto_now=True)
    # Writing answers are scored by a teacher
    needs_review = models.BooleanField(default=False)
    feedback = models.TextField(blank=True)
    graded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    graded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["attempt", "question"], name="uniq_answer_per_question")]
