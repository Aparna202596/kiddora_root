from django.urls import path
from appkiddora.views import cart_views
from appkiddora.views import order_views
from appkiddora.views import return_views
from appkiddora.views import review_views
from appkiddora.views import wallet_views
from appkiddora.views import wishlist_views
app_name = 'appkiddora'

urlpatterns = [
    #CART
    path("user/cart/",cart_views.cart_detail,name="cart_detail"),
    path("user/cart/add/",cart_views.add_to_cart,name="add_to_cart"),
    path("user/cart/update/",cart_views.update_cart_item,name="update_cart_item"),
    path("user/cart/increase/",cart_views.increase_quantity,name="increase_quantity"),
    path("user/cart/decrease/",cart_views.decrease_quantity,name="decrease_quantity"),
    path("user/cart/remove/",cart_views.remove_from_cart,name="remove_from_cart"),
    path("user/cart/checkout/",cart_views.checkout,name="checkout"), 

    #Admin order URLs
    path('admin/orders/', order_views.admin_order_list, name='admin_order_list'),
    path('admin/orders/order_details/<int:order_id>/',order_views.admin_order_detail,name='admin_order_detail'),
    path('admin/orders/update_order_status/<int:order_id>/',order_views.admin_update_order_status,name='admin_update_order_status'),
    path('admin/handle_return',order_views.admin_handle_return,name='admin_handle_return'),

    #User order URLs
    path('user/orders/', order_views.user_orders, name='user_orders'),
    path('user/orders/place_orders/', order_views.place_order, name='place_order'),
    path('user/orders/details/', order_views.order_detail, name='order_detail'),
    path('user/orders/cancel_order/', order_views.cancel_order, name='cancel_order'),
    path('user/orders/cancel_order_item/', order_views.cancel_order_item_view, name='cancel_order_item'),
    path('user/orders/invoice/', order_views.download_invoice, name='download_invoice'),

    #RETURN
    path("user/return/request/",return_views.request_return,name="request_return"),
    path("user/return/status/", return_views.return_status_view, name="return_status_view"),
    path("user/return/detail/", return_views.return_detail_view, name="return_detail_view"),

    path("admin/return_list/", return_views.admin_return_list, name="admin_return_list"),
    path("admin/return/verify/<int:return_id>/", return_views.admin_verify_return, name="admin_verify_return"),
    path("admin/return/analytics/", return_views.return_analytics_dashboard, name="return_analytics_dashboard"),

    #REVIEW
    path('product/review/add/', review_views.add_review, name='add_review'),
    path('product/review/edit/', review_views.edit_review, name='edit_review'),
    path('product/review/delete/', review_views.delete_review, name='delete_review'),
    
    path('admin/reviews/', review_views.user_review_list, name='user_review_list'),
    path('admin/reviews/detail/<int:review_id>/', review_views.user_review, name='user_review'),
    path('admin/review/delete/<int:review_id>/', review_views.delete_user_review, name='delete_user_review'),

    #WALLET
    path('admin/wallet/transactions/', wallet_views.admin_wallet_list, name='admin_wallet_list'),
    path('admin/wallet/transaction/', wallet_views.admin_wallet_detail, name='admin_wallet_detail'),

    #WISHLIST
    path("user/wishlist/", wishlist_views.wishlist_view, name="wishlist_view"),
    path("user/wishlist/add/", wishlist_views.add_to_wishlist, name="add_to_wishlist"),
    path("user/wishlist/remove/", wishlist_views.remove_from_wishlist, name="remove_from_wishlist"),
]