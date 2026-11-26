import logging

from .middleware import client_ip, current_request
from .models import AuditLog

log = logging.getLogger(__name__)


def _label(obj):
    if obj is None:
        return ""
    user = getattr(obj, "user", None)
    if user is not None and hasattr(user, "full_name"):
        return user.full_name
    for attr in ("full_name", "title", "name"):
        v = getattr(obj, attr, None)
        if v:
            return str(v)
    return str(obj)


def record(action, *, actor=None, target=None, target_type="", target_label="", detail=None):
    """Write one audit row. Never breaks the action being audited."""
    try:
        request = current_request()
        if actor is None and request is not None:
            u = getattr(request, "user", None)
            actor = u if (u is not None and getattr(u, "is_authenticated", False)) else None
        AuditLog.objects.create(
            actor=actor, actor_name=(actor.full_name if actor else "")[:200], actor_role=getattr(actor, "role", "") or "",
            action=action, target_type=target_type or (type(target).__name__.lower() if target is not None else ""),
            target_id=str(getattr(target, "pk", "") or "")[:40], target_label=(target_label or _label(target))[:200],
            detail=detail or {}, ip=client_ip(request),
        )
    except Exception:  # pragma: no cover - auditing must not break the real action
        log.exception("audit record failed: %s", action)
