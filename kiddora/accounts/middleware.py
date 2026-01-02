from django.shortcuts import redirect
from django.contrib.auth import logout
from django.urls import reverse
class BlockedUserMiddleware:
    """
    Middleware to log out and redirect any blocked (inactive) user.
    Ensures no blocked user can access any page.
    """
    def __init__(self, get_response):
        self.get_response = get_response
    def __call__(self, request):
        user = request.user
        blocked_url = reverse('accounts:blocked')
        if user.is_authenticated and not user.is_active:
            if request.path != blocked_url:
                logout(request)
                return redirect(blocked_url)
        return self.get_response(request)