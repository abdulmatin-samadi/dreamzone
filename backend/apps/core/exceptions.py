from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler


class DomainError(APIException):
    """Business-rule violation with a stable machine readable ``code``.

    The frontend translates ``code`` into the active UI language.
    """

    status_code = status.HTTP_409_CONFLICT
    default_detail = "Business rule violated."
    default_code = "domain_error"

    def __init__(self, code, detail=None, status_code=None):
        super().__init__(detail or code.replace("_", " ").capitalize(), code)
        self.code = code
        if status_code:
            self.status_code = status_code


def api_exception_handler(exc, context):
    if isinstance(exc, DjangoValidationError):
        exc = ValidationError(detail=exc.message_dict if hasattr(exc, "error_dict") else exc.messages)
    if isinstance(exc, IntegrityError):
        return Response(
            {"code": "integrity_error", "detail": "The operation conflicts with existing data."},
            status=status.HTTP_409_CONFLICT,
        )
    response = exception_handler(exc, context)
    if response is None:
        return None
    if isinstance(exc, ValidationError):
        response.data = {"code": "validation_error", "detail": "Validation failed.", "errors": response.data}
    elif isinstance(exc, DomainError):
        response.data = {"code": exc.code, "detail": str(exc.detail)}
    else:
        code = getattr(exc, "default_code", "error")
        detail = response.data.get("detail", str(exc)) if isinstance(response.data, dict) else str(exc)
        response.data = {"code": code, "detail": str(detail)}
    return response
