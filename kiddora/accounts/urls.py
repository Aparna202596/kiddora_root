from django.urls import path
from accounts.views import auth_views
from accounts.views import admin_views
from accounts.views import otp_views
from accounts.views import profile_views
from accounts.views import address_views

from django.views.generic import TemplateView

app_name = "accounts"

urlpatterns = [
    # AUTHENTICATION – USER
    path("login/", auth_views.user_login, name="login"),
    path("logout/", auth_views.user_logout, name="logout"),
    path("signup/", auth_views.signup_page, name="signup"),

    # AUTHENTICATION – ADMIN - STAFF
    path("admin/auth_login/", auth_views.admin_staff_login, name="auth_login"),
    path("admin/auth_logout/", auth_views.admin_staff_logout, name="auth_logout"),

    # AUTHENTICATION – ADMIN
    path("admin/add/", auth_views.admin_add, name="admin_add"),
    path("admin/edit/<int:id>/", auth_views.admin_edit, name="admin_edit"),
    path("admin/admin_page/", auth_views.admin_page, name="admin_page"),
    path("admin/delete/<int:user_id>/", auth_views.admin_delete, name="admin_delete"),
    
    # AUTHENTICATION – STAFF
    


    # ================= ADMIN =================
    path("admin/dashboard/", admin_views.admin_dashboard_view, name="dashboard"),
    path("admin/users/", admin_views.admin_user_list, name="user_list"),

    

    # OTP VERIFICATION
    path("verify-otp/", otp_views.verify_otp, name="verify_otp"),
    path("resend-otp/", otp_views.resend_otp, name="resend_otp"),

    # ================= FORGOT PASSWORD (OTP FLOW) =================
    path("forgot-password/", otp_views.verify_forgot_password_otp, name="verify_forgot_password_otp"),
    path("reset-password/", otp_views.reset_password, name="reset_password"),

    # ================= PROFILE =================
    path("profile/", profile_views.profile_view, name="profile"),
    path("profile/edit/", profile_views.profile_edit, name="profile_edit"),
    path("profile/change-password/", profile_views.change_password, name="change_password"),
    path("profile/change-email/", profile_views.change_email, name="change_email"),
    path("profile/verify-email-otp/", profile_views.verify_email_otp, name="verify_email_otp"),

    # ================= ADDRESS =================
    path("addresses/", address_views.address_list, name="address_list"),
    path("addresses/add/", address_views.address_add, name="address_add"),
    path("addresses/<int:address_id>/edit/", address_views.address_edit, name="address_edit"),
    path("addresses/<int:address_id>/delete/", address_views.address_delete, name="address_delete"),

    # ADMIN – USER MANAGEMENT
    path("admin/users_list/", admin_views.admin_user_list, name="admin_user_list"),
    path("admin/users/block/<int:user_id>/", admin_views.block_user, name="block_user"),
    path("admin/users/unblock/<int:user_id>/", admin_views.unblock_user, name="unblock_user"),
    path('admin/dashboard/',admin_views.admin_dashboard_view,name='dashboard'),
    path('admin/customer_list/',admin_views.user_management_view,name='user_list'),
    path('admin/users/delete/<int:user_id>/',admin_views.delete_user_view,name="delete_user"),
    
    path('blocked/',TemplateView.as_view(template_name="accounts/auth/blocked.html"),name="blocked")
]