from django.urls import path
from . import views

app_name = 'store'

urlpatterns = [
    path('',views.anonymous_user_home,name='anonymous_user_home'),
    path('home/',views.home,name='home'),

    path('about_us/',views.aboutus_view,name='about_us'),
    path('contactus/',views.contactus_view,name='contact'),
    path('privacy_policy/',views.privacy_policy_view,name='privacy_policy'),
    path('return_policy/',views.return_policy_view,name='return_policy'),
    path('cookie_policy/',views.cookie_policy_view,name='cookie_policy'),
    path('blog/',views.blog_view,name='blog'),
]