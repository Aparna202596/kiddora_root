from django.urls import path
from shopcore.views import store_views
app_name = 'shopcore'

urlpatterns = [

    path('',store_views.anonymous_home,name='anonymous_home'),
    path('user/home/',store_views.home,name='home'),

    path('aboutus/',store_views.aboutus_view,name='about_us'),
    path('contactus/',store_views.contactus_view,name='contact_us'),
    path('privacy-policy/',store_views.privacy_policy_view,name='privacy_policy'),
    path('return-policy/',store_views.return_policy_view,name='return_policy'),
    path('cookie-policy/',store_views.cookie_policy_view,name='cookie_policy'),
    path('blog/',store_views.blog_view,name='blog'),
    path('terms-conditions/',store_views.terms_conditions_view,name='terms_conditions'),


]