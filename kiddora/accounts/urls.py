from django.urls import path

from accounts.views import auth_views
from accounts.views import admin_views
from accounts.views import otp_views
from accounts.views import profile_views
from accounts.views import address_views

app_name = "accounts"

urlpatterns = [

    # AUTHENTICATION – USER
    path("login/", auth_views.login_view, name="login"),
    path("signup/", auth_views.signup, name="signup"),
    path("logout/", auth_views.logout_view, name="logout"),
    path("forgot-password/", auth_views.forgot_password, name="forgot_password"),
    path("reset-password/<str:token>/", auth_views.reset_password, name="reset_password"),

    # AUTHENTICATION – ADMIN
    path("admin/login/", auth_views.admin_login, name="admin_login"),

    # OTP VERIFICATION
    path("verify-otp/<int:user_id>/", otp_views.verify_otp, name="verify_otp"),
    path("resend-otp/<int:user_id>/", otp_views.resend_otp, name="resend_otp"),

    # USER PROFILE
    path("profile/", profile_views.profile_view, name="profile_view"),
    path("profile/edit/", profile_views.profile_edit, name="profile_edit"),
    path("profile/change-password/", profile_views.change_password, name="change_password"),

    # USER ADDRESS MANAGEMENT
    path("addresses/", address_views.address_list, name="address_list"),
    path("addresses/add/", address_views.address_add, name="address_add"),
    path("addresses/edit/<int:address_id>/", address_views.address_edit, name="address_edit"),
    path("addresses/delete/<int:address_id>/", address_views.address_delete, name="address_delete"),

    # ADMIN – USER MANAGEMENT
    path("admin/users/", admin_views.user_list, name="admin_user_list"),
    path("admin/users/block/<int:user_id>/", admin_views.block_user, name="block_user"),
    path("admin/users/unblock/<int:user_id>/", admin_views.unblock_user, name="unblock_user"),
]


