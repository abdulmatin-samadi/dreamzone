from datetime import timedelta

from django.conf import settings
from rest_framework_simplejwt.tokens import AccessToken


def issue_kiosk_token(student_user):
    """Short-lived access token for a walk-in student, issued to the receptionist.

    The ``kiosk`` claim limits it to examination-taking endpoints (see
    ``apps.core.permissions.KioskRestricted``). It has no refresh token.
    """
    token = AccessToken.for_user(student_user)
    token.set_exp(lifetime=timedelta(hours=settings.KIOSK_TOKEN_HOURS))
    token["kiosk"] = True
    return str(token)
