from django.shortcuts import redirect
from functools import wraps
from accounts.models import CustomUser
from django.urls import reverse

def user_login_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        blocked_url = reverse("accounts:blocked")
        if not request.user.is_authenticated:
            return redirect("accounts:login")
        if request.path == blocked_url:
            return view_func(request, *args, **kwargs)
        if request.user.role != CustomUser.ROLE_CUSTOMER:
            return redirect("accounts:blocked")
        return view_func(request, *args, **kwargs)
    return wrapper

def staff_login_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        blocked_url = reverse("accounts:blocked")
        if not request.user.is_authenticated:
            return redirect("accounts:auth_login")
        if request.path == blocked_url:
            return view_func(request, *args, **kwargs)
        if request.user.role != CustomUser.ROLE_STAFF:
            return redirect("accounts:blocked")
        return view_func(request, *args, **kwargs)
    return wrapper

def admin_login_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        blocked_url = reverse("accounts:blocked")
        if not request.user.is_authenticated:
            return redirect("accounts:auth_login")
        if request.path == blocked_url:
            return view_func(request, *args, **kwargs)
        if request.user.role != CustomUser.ROLE_ADMIN:
            return redirect("accounts:blocked")
        return view_func(request, *args, **kwargs)
    return wrapper