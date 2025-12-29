from django.shortcuts import redirect
from django.urls import reverse
from django.http import HttpResponseForbidden


class AdminAccessMiddleware:
    """
    Global middleware to protect all admin URLs.
    Checks if the user is authenticated and is a staff member.
    If not, redirects to admin login or returns 403 Forbidden.
    """

    ADMIN_URL_PREFIXES = (
        '/admin/',
        '/admin-panel/',
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path

        if path.startswith(self.ADMIN_URL_PREFIXES):
            user = request.user

            # Not logged in
            if not user.is_authenticated:
                #return redirect(reverse('accounts:admin_login'))
                return redirect('accounts:login')

            # Blocked or inactive user
            if not user.is_active:
                #return redirect(reverse('accounts:admin_login'))
                return redirect('accounts:login')
            # Not an admin/staff user
            if not user.is_staff:
                return HttpResponseForbidden("You are not authorized to access this page.")

        return self.get_response(request)
