from django.apps import AppConfig


class ExaminationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.examinations"

    def ready(self):
        from . import signals  # noqa: F401  a group's exams reach students who join later
