from django.shortcuts import render, redirect
from django.contrib import messages
from accounts.decorators import user_login_required
from django.utils import timezone
from accounts.views.otp_views import generate_otp

#@user_login_required
def profile_view(request):
    return render(request, "accounts/profile/profile.html", {"user": request.user})


#@user_login_required
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


#@user_login_required
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
    return render(request, "accounts/profile/change_password.html")

#@user_login_required
def change_email(request):
    if request.method == "POST":
        new_email = request.POST.get("email")

        request.user.pending_email = new_email
        request.user.otp = generate_otp()
        request.user.otp_created_at = timezone.now()
        request.user.save()

        return redirect("accounts:verify_email_otp")

    return render(request, "accounts/profile/change_email.html")


#@user_login_required
def verify_email_otp(request):
    user = request.user

    if request.method == "POST":
        if user.otp == request.POST.get("otp"):
            user.email = user.pending_email
            user.pending_email = None
            user.otp = None
            user.save()
            messages.success(request, "Email updated")
            return redirect("accounts:profile_view")

    return render(request, "accounts/profile/verify_email_otp.html")
