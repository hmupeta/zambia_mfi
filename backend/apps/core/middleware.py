# apps/core/middleware.py

from django.shortcuts import redirect
from django.urls import reverse
from django.contrib.auth import logout

class OrgStatusMiddleware:
    """
    Middleware to enforce organization status (e.g., active, suspended).
    """
    def __init__(self, get_response):
        # THIS LINE WAS MISSING OR BROKEN, causing the TypeError
        self.get_response = get_response

    def __call__(self, request):
        # 1. BYPASS JWT ROUTES
        # Because the frontend uses JWT (localStorage), Django's request.user 
        # is always AnonymousUser on these routes. If we don't bypass them, 
        # the middleware will endlessly redirect the user to /login/.
        bypass_prefixes = (
            '/app/',      # Web portal frontend pages (handled by JS)
            '/api/',      # API endpoints (handled by DRF JWT)
            '/login/',    # Auth pages
            '/logout/',
            '/signup/',
            '/static/',   # Static assets
            '/media/',    # Media files
            '/admin/',    # Django admin (handles its own auth)
            '/portal/',   # Customer portal
        )

        if any(request.path.startswith(prefix) for prefix in bypass_prefixes):
            return self.get_response(request)

        # 2. STANDARD SESSION AUTH CHECKS
        # For any other standard Django pages that rely on Session cookies:
        if request.user.is_authenticated:
            org = getattr(request.user, 'organization', None)
            
            # Check if the organization is suspended or inactive
            if org and not getattr(org, 'is_active', True):
                logout(request)
                return redirect(f"{reverse('ui-login')}?error=org_suspended")

        # 3. CONTINUE TO VIEW
        return self.get_response(request)