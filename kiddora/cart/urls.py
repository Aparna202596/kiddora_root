from django.urls import path
from . import views

app_name = 'cart'

urlpatterns = [
    path("user/cart/",views.cart_detail,name="cart_detail"),
    path("user/cart/add/",views.add_to_cart,name="add_to_cart"),
    path("user/cart/update/",views.update_cart_item,name="update_cart_item"),
    path("user/cart/increase/",views.increase_quantity,name="increase_quantity"),
    path("user/cart/decrease/",views.decrease_quantity,name="decrease_quantity"),
    path("user/cart/remove/",views.remove_from_cart,name="remove_from_cart"),
    path("user/cart/checkout/",views.checkout,name="checkout"), 
]