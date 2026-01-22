from django.shortcuts import redirect
from django.contrib.auth import logout
from django.urls import reverse

class BlockedUserMiddleware:
    """
    Logs out inactive users and redirects them to blocked page.
    Prevents redirect conflicts with admin/user decorators.
    """
    """
    IMPORTANT:
    BlockedUserMiddleware must NEVER block auth/OTP routes.
    Inactive users must be allowed to verify OTP.
    """
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        user = request.user

        # Public URLs that must bypass blocking
        allowed_paths = [
            "login/",
            "signup/",
            "logout/",
            "verify-otp/",
            "resend-otp/",
            "forgot-password/",
            "verify-forgot-password/"
            "reset-password/",
            "blocked/",
        ]
        if user.is_authenticated and not user.is_active:
            if request.path not in allowed_paths:
                logout(request)
                return redirect("accounts:blocked")
        return self.get_response(request)