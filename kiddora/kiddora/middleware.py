from django.shortcuts import redirect
from django.urls import reverse
from accounts.models import CustomUser

class AdminAccessMiddleware:
    """
    Protect admin URLs but allow admin login page itself.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        admin_login_url = reverse("accounts:admin_login")
        admin_logout_url = reverse("accounts:admin_logout")
        blocked_url = reverse("accounts:blocked")

        # Allow auth-related admin URLs
        if request.path in [admin_login_url, admin_logout_url, blocked_url]:
            return self.get_response(request)

        # Protect admin routes
        if request.path.startswith("/accounts/admin/"):
            if not request.user.is_authenticated:
                return redirect("accounts:admin_login")
            if request.user.role != CustomUser.ROLE_ADMIN:
                return redirect("accounts:blocked")

        return self.get_response(request)