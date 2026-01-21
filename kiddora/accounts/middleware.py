from django.shortcuts import redirect
from django.contrib.auth import logout
from django.urls import reverse

class BlockedUserMiddleware:
    """
    Logs out inactive users and redirects them to blocked page.
    Prevents redirect conflicts with admin/user decorators.
    """
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        blocked_url = reverse("accounts:blocked")
        # Allow access to blocked page itself
        if request.path == blocked_url:
            return self.get_response(request)
        user = request.user
        if user.is_authenticated and not user.is_active:
            logout(request)
            return redirect(blocked_url)
        return self.get_response(request)