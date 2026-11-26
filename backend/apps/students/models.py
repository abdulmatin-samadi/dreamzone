from django.conf import settings
from django.db import models


class StudentProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="student_profile")
    current_level = models.ForeignKey(
        "academics.Level", on_delete=models.PROTECT, null=True, blank=True, related_name="students"
    )
    initial_level = models.ForeignKey(
        "academics.Level", on_delete=models.PROTECT, null=True, blank=True, related_name="+",
        help_text="Level estimated by the receptionist at registration.",
    )
    registered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="registered_students"
    )
    is_guest = models.BooleanField(
        default=False, help_text="Walk-in who only sat a placement test; not enrolled / no login yet."
    )
    notes = models.TextField(blank=True)
    groups = models.ManyToManyField("academics.Group", through="StudentGroup", related_name="students")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["current_level"])]

    def __str__(self):
        return self.user.full_name


class StudentGroup(models.Model):
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name="memberships")
    group = models.ForeignKey("academics.Group", on_delete=models.CASCADE, related_name="memberships")
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["student", "group"], name="uniq_student_group")]


class LevelChangeHistory(models.Model):
    class Reason(models.TextChoices):
        PLACEMENT = "PLACEMENT", "Placement test"
        UPGRADE = "UPGRADE", "Approved upgrade examination"
        ADMIN = "ADMIN", "Administrative change"
        REVERT = "REVERT", "Reverted by administrator"

    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name="level_history")
    from_level = models.ForeignKey("academics.Level", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    to_level = models.ForeignKey("academics.Level", on_delete=models.PROTECT, related_name="+")
    reason = models.CharField(max_length=12, choices=Reason.choices)
    result = models.ForeignKey(
        "results.ExamResult", on_delete=models.SET_NULL, null=True, blank=True, related_name="level_changes"
    )
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name_plural = "level change history"
        indexes = [models.Index(fields=["student", "-created_at"])]
