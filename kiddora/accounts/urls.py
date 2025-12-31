from django.urls import path
from .views import auth_views,otp_views,profile_views,admin_views,address_views  

app_name = 'accounts'

urlpatterns = [
    
    path('signup/', auth_views.signup_view, name='signup'),
    path('login/', auth_views.login_view, name='login'),
    path('admin_login/', auth_views.admin_login, name='admin_login'),
    path('forgot_password/', auth_views.forgot_password, name='forgot_password'),
    path('reset_password/', auth_views.reset_password, name='reset_password'),

    path('verify_otp/', otp_views.verify_otp, name='verify_otp'),

    path('profile/', profile_views.profile_view, name='profile'),
    path('profile_edit/', profile_views.profile_edit, name='profile_edit'),
    path('change_password/', profile_views.change_password, name='change_password'),

    path('address_list/', address_views.address_list, name='address_list'),
    path('address_add/', address_views.address_add, name='address_add'),
    path('address_edit/', address_views.address_edit, name='address_edit'),
    path('address_delete/', address_views.address_delete, name='address_delete'),
]

