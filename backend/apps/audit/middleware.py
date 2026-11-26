from contextvars import ContextVar

_current = ContextVar("dz_request", default=None)


def current_request():
    return _current.get()


def client_ip(request):
    if request is None:
        return None
    fwd = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return (fwd.split(",")[0].strip() if fwd else request.META.get("REMOTE_ADDR")) or None


class CurrentRequestMiddleware:
    """Remembers the request so audit records get the IP without passing it everywhere."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = _current.set(request)
        try:
            return self.get_response(request)
        finally:
            _current.reset(token)
