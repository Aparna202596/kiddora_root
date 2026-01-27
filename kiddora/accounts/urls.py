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
    path("login/", auth_views.user_login, name="login"),
    path("logout/", auth_views.user_logout, name="logout"),
    path("signup/", auth_views.user_signup, name="signup"),

    #AUTHENTICATION - SOCIAL LOGIN
    path("login/google_login/", auth_views.google_login, name="google_login"),
    path("login/facebook_login/", auth_views.facebook_login, name="facebook_login"),

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
    path("verify_signup_otp/", otp_views.verify_signup_otp, name="verify_signup_otp"),
    path("resend_otp/", otp_views.resend_signup_otp, name="resend_signup_otp"),

    # FORGOT PASSWORD (OTP FLOW)
    path("forgot_password/",otp_views.forgot_password,name="forgot_password"),
    path("verify_forgot_password/", otp_views.verify_forgot_password_otp, name="verify_forgot_password_otp"),
    path("reset_password/", otp_views.reset_password, name="reset_password"),

    #PROFILE
    path("profile/", profile_views.user_profile, name="user_profile"),
    path("profile/edit/", profile_views.edit_profile, name="edit_profile"),
    path("profile/change_password/", profile_views.change_password, name="change_password"),
    path("profile/change_email/", profile_views.change_email, name="change_email"),
    path("profile/verify_email_otp/", profile_views.verify_email_update, name="verify_email_update"),

    #ADDRESS
    path("addresses/", address_views.address_list, name="address_list"),
    path("addresses/set_default/<int:address_id>/", address_views.set_default_address, name="set_default_address"),
    path("addresses/add/", address_views.address_add, name="address_add"),
    path("addresses/edit/<int:address_id>/", address_views.address_edit, name="address_edit"),
    path("addresses/delete/<int:address_id>", address_views.address_delete, name="address_delete"),

    #ERROR
    path('error/403/',error_views.handler403,name='403'),
    path('error/404/',error_views.handler404,name='404'),
    path('error/500/',error_views.handler500,name='500'),

    path('error/blocked/',TemplateView.as_view(template_name="accounts/errors/blocked.html"),name="blocked")
]