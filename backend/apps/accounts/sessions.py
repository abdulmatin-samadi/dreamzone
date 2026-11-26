"""Login sessions: which devices a user is signed in on, and signing them out."""
import re
from datetime import timedelta
from urllib.parse import unquote

from django.conf import settings
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit.middleware import client_ip

from .models import LoginSession

TOUCH_EVERY = timedelta(seconds=60)


def device_headers(request):
    """The browser's own random id (localStorage) and the name the front desk gave the computer."""
    if request is None:
        return "", ""
    did = re.sub(r"[^A-Za-z0-9_-]", "", request.headers.get("X-Device-Id", ""))[:64]
    try:
        name = unquote(request.headers.get("X-Device-Name", ""))
    except Exception:
        name = ""
    return did, name.strip()[:80]


def describe_agent(ua):
    """'Chrome · Windows' from a User-Agent string (good enough for people to recognise their device)."""
    ua = ua or ""
    browser = next((name for pat, name in (
        (r"Edg/", "Edge"), (r"OPR/|Opera", "Opera"), (r"YaBrowser", "Yandex"), (r"SamsungBrowser", "Samsung Internet"),
        (r"Firefox/|FxiOS", "Firefox"), (r"Chrome/|CriOS", "Chrome"), (r"Safari/", "Safari"),
    ) if re.search(pat, ua)), "")
    system = next((name for pat, name in (
        (r"iPad", "iPad"), (r"iPhone", "iPhone"), (r"Android", "Android"), (r"Windows", "Windows"),
        (r"Mac OS X|Macintosh", "macOS"), (r"CrOS", "ChromeOS"), (r"Linux", "Linux"),
    ) if re.search(pat, ua)), "")
    return " · ".join(x for x in (browser, system) if x) or (ua[:40] if ua else "")


def device_label(request):
    did, name = device_headers(request)
    agent = describe_agent(request.META.get("HTTP_USER_AGENT", "")) if request is not None else ""
    return " — ".join(x for x in (name, agent) if x)


def start_session(user, request):
    """Create the session and its refresh token (the access token inherits the ``sid`` claim)."""
    did, name = device_headers(request)
    s = LoginSession.objects.create(
        user=user, device_id=did, device_name=name, last_seen_at=timezone.now(),
        user_agent=(request.META.get("HTTP_USER_AGENT", "") if request is not None else "")[:300], ip=client_ip(request),
    )
    refresh = RefreshToken.for_user(user)
    refresh["sid"] = str(s.pk)
    return refresh, s


def active_sessions(user):
    since = timezone.now() - settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"]
    return LoginSession.objects.filter(user=user, revoked_at__isnull=True, last_seen_at__gte=since)


def revoke(qs):
    return qs.filter(revoked_at__isnull=True).update(revoked_at=timezone.now())


def session_alive(sid):
    """None = unknown id. Touches ``last_seen_at`` at most once a minute."""
    s = LoginSession.objects.filter(pk=sid).only("id", "revoked_at", "last_seen_at").first()
    if s is None or s.revoked_at is not None:
        return False
    now = timezone.now()
    if now - s.last_seen_at > TOUCH_EVERY:
        LoginSession.objects.filter(pk=s.pk).update(last_seen_at=now)
    return True
