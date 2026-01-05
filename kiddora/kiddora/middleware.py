from django.shortcuts import redirect
from django.http import HttpResponseForbidden
from accounts.models import CustomUser

class AdminAccessMiddleware:
    """
    Middleware to protect all admin URLs.
    Only allows authenticated, active, admin users to access URLs starting with /admin/ or /admin-panel/.
    """
    ADMIN_URL_PREFIXES = ('/admin/',)

    def __init__(self, get_response):
            self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith("/accounts/admin/"):
            if not request.user.is_authenticated:
                return redirect("accounts:admin_login")
            if request.user.role != "admin":
                return redirect("accounts:admin_login")
        return self.get_response(request)
    
    # def __init__(self, get_response):
    #     self.get_response = get_response
    # def __call__(self, request):
    #     path = request.path
    #     user = request.user
    #     if path.startswith(self.ADMIN_URL_PREFIXES):
    #         if not user.is_authenticated:
    #             return redirect('accounts:admin_login')
    #         if not user.is_active:
    #             return redirect('accounts:blocked')
    #         if user.role != CustomUser.ROLE_ADMIN:
    #             return HttpResponseForbidden("You are not authorized to access this page.")
    #     return self.get_response(request)

    