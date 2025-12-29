from django.shortcuts import redirect
from accounts.models import CustomUser
from django.contrib import messages

# Decorator to ensure user is logged in and not blocked
# Used for normal users
def user_login_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, "Please login to continue")
            return redirect('accounts:login')

        if not request.user.is_active:
            messages.error(request, "Your account is blocked")
            return redirect('accounts:login')

        return view_func(request, *args, **kwargs)
    return wrapper
from django.shortcuts import redirect
from django.contrib import messages

# Decorator to ensure admin user is logged in
# used for admin dashboard and management
def admin_login_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('accounts:login')

        if request.user.role != CustomUser.ROLE_ADMIN:
            return redirect('accounts:blocked')

        return view_func(request, *args, **kwargs)
    return wrapper
# Alias for clarity
admin_required = admin_login_required
