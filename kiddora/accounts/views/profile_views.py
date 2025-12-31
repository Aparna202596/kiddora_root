from django.shortcuts import render, redirect
from django.contrib import messages
from accounts.decorators import user_login_required


@user_login_required
def profile_view(request):
    return render(request, "accounts/profile/profile.html", {"user": request.user})


@user_login_required
def profile_edit(request):
    user = request.user
    if request.method == "POST":
        user.full_name = request.POST.get("full_name")
        user.phone = request.POST.get("phone")
        if "profile_image" in request.FILES:
            user.profile_image = request.FILES["profile_image"]
        user.save()
        messages.success(request, "Profile updated")
        return redirect("accounts:profile_view")
    return render(request, "accounts/profile/edit_profile.html", {"user": user})


@user_login_required
def change_password(request):
    user = request.user
    if request.method == "POST":
        current_password = request.POST.get("current_password")
        new_password = request.POST.get("new_password")
        confirm_password = request.POST.get("confirm_password")
        if user.check_password(current_password):
            if new_password == confirm_password:
                user.set_password(new_password)
                user.save()
                messages.success(request, "Password changed successfully")
                return redirect("accounts:login")
            messages.error(request, "New passwords do not match")
        else:
            messages.error(request, "Current password incorrect")
    return render(request, "accounts/profile/edit_profile.html")

