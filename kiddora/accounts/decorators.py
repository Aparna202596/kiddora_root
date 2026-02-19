from django.contrib.auth import logout
from django.shortcuts import redirect
from accounts.models import *
from django.urls import reverse
from functools import wraps

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

def admin_login_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):

        if not request.user.is_authenticated:
            return redirect("accounts:admin_login")
        
        if request.user.role != CustomUser.ROLE_ADMIN:
            logout(request)

            return redirect("accounts:blocked")
        return view_func(request, *args, **kwargs)
    return wrapper
