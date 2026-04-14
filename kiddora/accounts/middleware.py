from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import reverse

class BlockedUserMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user

        # Public URLs that must bypass blocking
        allowed_prefixes = (
            "/accounts/user/login/",
            "/accounts/user/signup/",
            "/accounts/user/verify-signup/",
            "/accounts/blocked/",
            "/accounts/errors/",
            "/shop/",           # anonymous home
            "/static/",
            "/media/",
        )
        if user.is_authenticated and not user.is_active:
            if not request.path.startswith(allowed_prefixes):
                logout(request)
                return redirect("accounts:blocked")
        return self.get_response(request)
