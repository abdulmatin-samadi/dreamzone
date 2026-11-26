import secrets

from django.db import models

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I: easy to read out and type


def new_join_code(length=6):
    while True:
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(length))
        if not Group.objects.filter(join_code=code).exists():
            return code


class Level(models.Model):
    """CEFR level (A1..C2). ``order`` defines progression."""

    code = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=64)
    description = models.TextField(blank=True)
    order = models.PositiveSmallIntegerField(unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"{self.code} — {self.name}"

    def previous(self):
        return Level.objects.filter(order__lt=self.order, is_active=True).order_by("-order").first()

    def next(self):
        return Level.objects.filter(order__gt=self.order, is_active=True).order_by("order").first()


class Group(models.Model):
    name = models.CharField(max_length=120, unique=True)
    level = models.ForeignKey(Level, on_delete=models.PROTECT, related_name="groups")
    teacher = models.ForeignKey(
        "accounts.TeacherProfile", on_delete=models.SET_NULL, null=True, blank=True, related_name="groups"
    )
    join_code = models.CharField(max_length=12, unique=True, null=True, blank=True,
                                 help_text="Students type this code to join the group (generated automatically).")
    schedule = models.CharField(max_length=120, blank=True, help_text="Lesson days and time, e.g. 'Du-Chor-Ju 18:00-19:30'")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        indexes = [models.Index(fields=["teacher", "is_active"])]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.join_code:
            self.join_code = new_join_code()
        super().save(*args, **kwargs)
