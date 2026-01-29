from django.urls import path
from accounts.views import auth_views
from accounts.views import admin_views
from accounts.views import otp_views
from accounts.views import profile_views
from accounts.views import address_views
from accounts.views import error_views
from django.views.generic import TemplateView


app_name = "accounts"

urlpatterns = [
    #AUTHENTICATION – USER
    path("user/login/", auth_views.user_login, name="login"),
    path("user/logout/", auth_views.user_logout, name="logout"),
    path("user/signup/", auth_views.user_signup, name="signup"),

    #AUTHENTICATION - SOCIAL LOGIN
    path("accounts/google/login/", auth_views.google_login, name="google_login"),

    #AUTHENTICATION – ADMIN
    path("admin/auth_login/", auth_views.admin_login, name="auth_login"),
    path("admin/auth_logout/", auth_views.admin_logout, name="auth_logout"),

    # AUTHENTICATION – ADMIN
    path("admin/admin_dashboard/", admin_views.admin_dashboard_view, name="admin_dashboard"),
    path("admin/sales_report/",admin_views.admin_sales_report,name="sales_report"),
    
    # ADMIN – USER MANAGEMENT
    path("admin/customers/", admin_views.admin_user_list, name="admin_user_list"),
    path("admin/customers/customer_details/<int:user_id>/", admin_views.admin_user_detail, name="admin_user_detail"),
    path("admin/customers/block/<int:user_id>/", admin_views.admin_block_user, name="admin_block_user"),
    path("admin/customers/unblock/<int:user_id>/", admin_views.admin_unblock_user, name="admin_unblock_user"),
    path('admin/customers/delete/<int:user_id>/',admin_views.delete_user_view,name="delete_user"),
    
    # OTP VERIFICATION
    path("user/verify_signup_otp/", otp_views.verify_signup_otp, name="verify_signup_otp"),
    path("user/resend_otp/", otp_views.resend_signup_otp, name="resend_signup_otp"),

    # FORGOT PASSWORD (OTP FLOW)
    path("user/forgot_password/",otp_views.forgot_password,name="forgot_password"),
    path("user/verify_forgot_password/", otp_views.verify_forgot_password_otp, name="verify_forgot_password_otp"),
    path("user/reset_password/", otp_views.reset_password, name="reset_password"),

    #PROFILE
    path("user/profile/", profile_views.user_profile, name="user_profile"),
    path("user/profile/edit/", profile_views.edit_profile, name="edit_profile"),
    path("user/profile/change_password/", profile_views.change_password, name="change_password"),
    path("user/profile/change_email/", profile_views.change_email, name="change_email"),
    path("user/profile/verify_email_otp/", profile_views.verify_email_update, name="verify_email_update"),

    #ADDRESS
    path("user/addresses/", address_views.address_list, name="address_list"),
    path("user/addresses/set_default/", address_views.set_default_address, name="set_default_address"),
    path("user/addresses/add/", address_views.address_add, name="address_add"),
    path("user/addresses/edit/", address_views.address_edit, name="address_edit"),
    path("user/addresses/delete/", address_views.address_delete, name="address_delete"),
    #ERROR
    path('error/403/',error_views.handler403,name='403'),
    path('error/404/',error_views.handler404,name='404'),
    path('error/500/',error_views.handler500,name='500'),

    path('error/blocked/',TemplateView.as_view(template_name="accounts/errors/blocked.html"),name="blocked")
]