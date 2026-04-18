from accounts.decorators import admin_login_required
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache

User = get_user_model()


#  ────────────────────────────────────────────────── ADMIN PROFILE ──────────────────────────────────────────────────
@never_cache
@admin_login_required
def admin_profile(request):
    admin = request.user
    context = {
        "admin": admin,
    }
    return render(
        request,
        "accounts/admin_profile/admin_profile.html",
        context,
    )


#  ────────────────────────────────────────────────── EDIT ADMIN PROFILE ──────────────────────────────────────────────────
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


#  ────────────────────────────────────────────────── ADMIN ACTIVITY INFO ──────────────────────────────────────────────────
@never_cache
@admin_login_required
def admin_activity_info(request):
    admin = request.user

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
        "accounts/admin_profile/admin_activity.html",
        context,
    )
