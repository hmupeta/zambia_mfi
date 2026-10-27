# apps/portal/middleware.py
from .auth import get_current_client


class PortalClientMiddleware:
    """
    If a session-based client is logged in, attach it to `request.portal_client`
    for every request. Read-only — the `portal_login_required` decorator
    decides whether to enforce it.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.portal_client = get_current_client(request)
        return self.get_response(request)