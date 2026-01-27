from django.urls import path
from . import views

app_name = 'cart'

urlpatterns = [
    path("cart/",views.cart_detail,name="cart_detail"),
    path("cart/add/<int:variant_id>/",views.add_to_cart,name="add_to_cart"),
    path("cart/update/<int:item_id>/",views.update_cart_item,name="update_cart_item"),
    path("cart/increase/<int:item_id>/",views.increase_quantity,name="increase_quantity"),
    path("cart/decrease/<int:item_id>/",views.decrease_quantity,name="decrease_quantity"),
    path("cart/remove/<int:item_id>/",views.remove_from_cart,name="remove_from_cart"),

    path("cart/checkout/",views.checkout,name="checkout"), 
]