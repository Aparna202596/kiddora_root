from django.urls import path
from . import views

app_name = 'wishlist'

urlpatterns = [

    path("user/wishlist/", views.wishlist_view, name="wishlist_view"),
    path("user/wishlist/add/", views.add_to_wishlist, name="add_to_wishlist"),
    path("user/wishlist/remove/", views.remove_from_wishlist, name="remove_from_wishlist"),
]