from django.shortcuts import redirect
from django.contrib import messages
from accounts.models import CustomUser

def user_login_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, "Please login to continue")
            return redirect("accounts:login")
        if not request.user.is_active:
            messages.error(request, "Your account is blocked")
            return redirect("accounts:login")
        return view_func(request, *args, **kwargs)
    return wrapper

def admin_login_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("accounts:login")
        if request.user.role != CustomUser.ROLE_ADMIN:
            return redirect("accounts:blocked")
        return view_func(request, *args, **kwargs)
    return wrapper


