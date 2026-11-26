from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """Who did what, and when. Written by ``apps.audit.services.record``; never edited."""

    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    actor_name = models.CharField(max_length=200, blank=True, help_text="Kept even if the user is deleted later.")
    actor_role = models.CharField(max_length=16, blank=True)
    action = models.CharField(max_length=40, db_index=True)
    target_type = models.CharField(max_length=30, blank=True)
    target_id = models.CharField(max_length=40, blank=True)
    target_label = models.CharField(max_length=200, blank=True)
    detail = models.JSONField(default=dict, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["target_type", "target_id"]), models.Index(fields=["actor", "-created_at"])]

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.actor_name or 'system'} {self.action}"
