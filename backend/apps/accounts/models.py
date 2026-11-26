from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


class Role(models.TextChoices):
    ADMIN = "ADMIN", "Admin"
    RECEPTIONIST = "RECEPTIONIST", "Receptionist"
    TEACHER = "TEACHER", "Teacher"
    STUDENT = "STUDENT", "Student"


class User(AbstractUser):
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.STUDENT, db_index=True)
    phone = models.CharField(max_length=20, blank=True, db_index=True)
    language = models.CharField(max_length=5, default=settings.DEFAULT_UI_LANGUAGE)

    class Meta:
        ordering = ["first_name", "last_name"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(role__in=[r.value for r in Role]), name="user_role_valid"
            )
        ]

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.username

    @property
    def is_admin_role(self):
        return self.role == Role.ADMIN

    def save(self, *args, **kwargs):
        # Admin role users get Django admin access so the /admin/ site stays usable.
        if self.role == Role.ADMIN:
            self.is_staff = True
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.full_name} ({self.role})"


class TeacherProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="teacher_profile")
    bio = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.user.full_name


class PendingRegistration(models.Model):
    """A self-registration waiting for the e-mailed code. The account is created only after the code."""

    import uuid as _uuid

    id = models.UUIDField(primary_key=True, default=_uuid.uuid4, editable=False)
    email = models.EmailField(db_index=True)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    password = models.CharField(max_length=128, help_text="Hashed, like User.password.")
    initial_level = models.ForeignKey("academics.Level", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    code_hash = models.CharField(max_length=128)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    sent_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class LoginSession(models.Model):
    """One sign-in on one device. Its id travels in the JWT (``sid``); a revoked session stops working at once."""

    import uuid as _uuid

    id = models.UUIDField(primary_key=True, default=_uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="login_sessions")
    device_id = models.CharField(max_length=64, blank=True, db_index=True)
    device_name = models.CharField(max_length=80, blank=True, help_text="Name the reception gave this computer.")
    user_agent = models.CharField(max_length=300, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-last_seen_at"]
        indexes = [models.Index(fields=["user", "revoked_at"])]
