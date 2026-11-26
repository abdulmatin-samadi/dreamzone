from django.conf import settings
from django.db import models


class Recommendation(models.TextChoices):
    NONE = "NONE", "No recommendation"
    CONFIRM = "CONFIRM", "Level confirmed"
    LOWER = "LOWER", "Try the previous level"
    HIGHER = "HIGHER", "Try the next level"


class OfferStatus(models.TextChoices):
    NONE = "NONE", "No offer"
    PENDING = "PENDING", "Awaiting answer"
    ACCEPTED = "ACCEPTED", "Accepted"
    DECLINED = "DECLINED", "Declined"


class ApprovalStatus(models.TextChoices):
    NOT_REQUIRED = "NOT_REQUIRED", "Not required"
    PENDING = "PENDING", "Pending teacher approval"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"


class ExamResult(models.Model):
    attempt = models.OneToOneField("examinations.ExamAttempt", on_delete=models.PROTECT, related_name="result")
    student = models.ForeignKey("students.StudentProfile", on_delete=models.CASCADE, related_name="results")
    examination = models.ForeignKey("examinations.Examination", on_delete=models.PROTECT, related_name="results")
    level = models.ForeignKey("academics.Level", on_delete=models.PROTECT, related_name="+")

    total_score = models.DecimalField(max_digits=8, decimal_places=2)
    max_score = models.DecimalField(max_digits=8, decimal_places=2)
    percentage = models.DecimalField(max_digits=5, decimal_places=2)
    correct_count = models.PositiveIntegerField(default=0)
    incorrect_count = models.PositiveIntegerField(default=0)
    unanswered_count = models.PositiveIntegerField(default=0)
    section_scores = models.JSONField(default=dict)
    passed = models.BooleanField()
    # speaking: scored by the teacher / admin on the result page, added to total_score / max_score
    speaking_score = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    speaking_max = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    speaking_feedback = models.TextField(blank=True)
    speaking_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    speaking_at = models.DateTimeField(null=True, blank=True)
    writing_pending = models.BooleanField(default=False, db_index=True, help_text="Written answers still wait for the teacher's score.")

    # placement workflow
    recommendation = models.CharField(max_length=8, choices=Recommendation.choices, default=Recommendation.NONE)
    recommended_level = models.ForeignKey("academics.Level", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    offer_status = models.CharField(max_length=8, choices=OfferStatus.choices, default=OfferStatus.NONE)
    placed_level = models.ForeignKey(
        "academics.Level", on_delete=models.PROTECT, null=True, blank=True, related_name="+",
        help_text="Level the student was finally placed at by this placement result.",
    )

    # upgrade workflow
    approval_status = models.CharField(max_length=14, choices=ApprovalStatus.choices, default=ApprovalStatus.NOT_REQUIRED, db_index=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["student", "-created_at"]),
            models.Index(fields=["examination", "passed"]),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(max_score__gte=0), name="result_max_score_nonneg"),
            models.CheckConstraint(
                condition=models.Q(percentage__gte=0, percentage__lte=100), name="result_percentage_range"
            ),
        ]

    @property
    def is_locked(self):
        return self.approval_status in (ApprovalStatus.APPROVED, ApprovalStatus.REJECTED)
