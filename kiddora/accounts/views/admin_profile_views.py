from django.contrib.sessions.models import Session
from django.views.decorators.cache import never_cache
from django.contrib.auth import get_user_model
from accounts.decorators import admin_login_required
from appkiddora.models import *
from django.shortcuts import render
from django.shortcuts import render, redirect
from django.contrib import messages
from django.utils import timezone

User = get_user_model()

@never_cache
@admin_login_required
def admin_profile(request):
    admin = request.user  
    context = {"admin": admin,}
    return render(request,"accounts/admin_profile/admin_profile.html",context,)

@never_cache
@admin_login_required
def admin_edit_profile(request):
    admin = request.user

    if request.method == "POST":
        admin.full_name = request.POST.get("full_name")
        admin.phone = request.POST.get("phone")

        if "profile_image" in request.FILES:
            admin.profile_image = request.FILES["profile_image"]

        admin.save()
        messages.success(request, "Admin profile updated successfully")
        return redirect("accounts:admin_profile")

    return render(
        request,
        "accounts/admin_profile/edit_admin_profile.html",
        {"admin": admin},
    )


@never_cache
@admin_login_required
def admin_activity_log(request):
    """
    Shows recent system activity (orders handled in the system).
    """
    recent_orders = Order.objects.select_related("user").order_by("-created_at")[:50]

    return render(
        request,
        "accounts/admin_profile/admin_activity_log.html",
        {"recent_orders": recent_orders},
    )

@never_cache
@admin_login_required
def admin_security_info(request):
    admin = request.user

    # Active sessions (best-effort, Django-native)
    active_sessions = []
    for session in Session.objects.filter(expire_date__gte=timezone.now()):
        data = session.get_decoded()
        if str(admin.id) == str(data.get("_auth_user_id")):
            active_sessions.append(session)

    context = {
        "admin": admin,
        "last_login": admin.last_login,
        "date_joined": admin.date_joined,
        "active_sessions_count": len(active_sessions),
    }

    return render(
        request,
        "accounts/admin_profile/admin_security.html",
        context,
    )