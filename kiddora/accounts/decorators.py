from django.shortcuts import redirect
from accounts.models import CustomUser
from functools import wraps

def user_login_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("accounts:login")
        return view_func(request, *args, **kwargs)
    return wrapper

def staff_login_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("accounts:admin_login")
        if request.user.role != CustomUser.ROLE_STAFF:
            return redirect("accounts:blocked")
        return view_func(request, *args, **kwargs)
    return wrapper

def admin_login_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("accounts:admin_login")
        if request.user.role != CustomUser.ROLE_ADMIN:
            return redirect("accounts:blocked")
        return view_func(request, *args, **kwargs)
    return wrapper


