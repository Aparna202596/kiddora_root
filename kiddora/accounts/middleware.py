from django.shortcuts import redirect
from django.contrib.auth import logout
from accounts.models import CustomUser

class BlockedUserMiddleware:
    """
    Middleware to log out and redirect any blocked (inactive) user.
    Ensures no blocked user can access any page.
    """
    def __init__(self, get_response):
        self.get_response = get_response
    def __call__(self, request):
        user = request.user
        if user.is_authenticated and not user.is_active:
            logout(request)
            return redirect('accounts:blocked')  # create a blocked.html page explaining status
        return self.get_response(request)