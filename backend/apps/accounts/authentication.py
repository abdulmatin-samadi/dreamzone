from django.core.exceptions import ValidationError
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed, InvalidToken
from rest_framework_simplejwt.serializers import TokenRefreshSerializer

from .sessions import session_alive


def _check_sid(token):
    sid = token.get("sid") if hasattr(token, "get") else None
    if sid is None:
        return  # kiosk tokens and tokens issued before sessions existed
    try:
        ok = session_alive(sid)
    except (ValidationError, ValueError):
        ok = False
    if not ok:
        raise AuthenticationFailed("This device was signed out.", code="session_revoked")


class SessionJWTAuthentication(JWTAuthentication):
    """JWT + "sign out of this device / all devices": a revoked session is refused immediately."""

    def get_validated_token(self, raw_token):
        token = super().get_validated_token(raw_token)
        _check_sid(token)
        return token


class SessionTokenRefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        from rest_framework_simplejwt.tokens import RefreshToken

        try:
            _check_sid(RefreshToken(attrs["refresh"], verify=True))
        except AuthenticationFailed:
            raise InvalidToken("This device was signed out.")
        except Exception:
            pass  # an invalid token is reported by the parent class
        return super().validate(attrs)
