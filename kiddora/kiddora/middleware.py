from django.shortcuts import redirect
from django.http import HttpResponseForbidden
from accounts.models import CustomUser
from django.urls import reverse
class AdminAccessMiddleware:
    """
    Middleware to protect all admin URLs.
    Only allows authenticated, active, admin users to access URLs starting with /admin/ or /admin-panel/.
    """
    ADMIN_URL_PREFIXES = ("/admin/", "/accounts/admin/")

    def __init__(self, get_response):
            self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith("/accounts/admin/"):
            if request.path == reverse("accounts:blocked"):
                return self.get_response(request)
            if not request.user.is_authenticated:
                return redirect("accounts:auth_login")
            if request.user.role != CustomUser.ROLE_ADMIN:
                return redirect("accounts:auth_login")
        return self.get_response(request)