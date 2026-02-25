from django.urls import path
from shopcore.views import cart_views
from shopcore.views import order_views
from shopcore.views import return_views
from shopcore.views import review_views
from shopcore.views import wallet_views
from shopcore.views import wishlist_views
from shopcore.views import coupon_views
from shopcore.views import offer_views
from shopcore.views import store_views
app_name = 'shopcore'

urlpatterns = [

        #Admin coupon management views
    path("admin/coupon/", coupon_views.admin_coupon_list, name="admin_coupon_list"),
    path("admin/coupon/create-coupon/", coupon_views.admin_create_coupon, name="admin_create_coupon"),
    path("admin/coupon/delete-coupon/", coupon_views.admin_delete_coupon, name="admin_delete_coupon"),
    # User-facing coupon endpoints
    path("coupon/apply/", coupon_views.apply_coupon, name="apply_coupon"),
    path("coupon/remove/", coupon_views.remove_coupon, name="remove_coupon"),
    path("coupon/coupon-list/",coupon_views.available_coupons, name="available_coupons"),

    #Admin offer management views
    path("admin/offer-list/", offer_views.admin_offer_list, name="admin_offer_list"),
    path("admin/product-offer/", offer_views.admin_product_offer, name="admin_product_offer"),
    path("admin/category-offer/", offer_views.admin_category_offer, name="admin_category_offer"),
    path("admin/referral-offer/", offer_views.admin_referral_offer, name="admin_referral_offer"),
    path("admin/remove-offer/<int:offer_id>/", offer_views.admin_remove_offer, name="admin_remove_offer"),
    # User-facing offer endpoints 
    path("products/offer/best-offer", offer_views.get_best_offer_for_product, name="get_best_offer_for_product"),
    path("products/offer/calculate-offer-price", offer_views.calculate_offer_price, name="calculate_offer_price"),
    path("products/offer/calculate-cart-total", offer_views.calculate_cart_total, name="calculate_cart_total"),
    path("products/offer/apply-coupon-to-total", offer_views.apply_coupon_to_total, name="apply_coupon_to_total"),
    path("products/offer/checkout-total", offer_views.calculate_checkout_total, name="calculate_checkout_total"),

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
    path('admin/orders/order-details/<int:order_id>/',order_views.admin_order_detail,name='admin_order_detail'),
    path('admin/orders/update-order-status/<int:order_id>/',order_views.admin_update_order_status,name='admin_update_order_status'),
    path('admin/handle-return',order_views.admin_handle_return,name='admin_handle_return'),

    #User order URLs
    path('user/orders/', order_views.user_orders, name='user_orders'),
    path('user/orders/place-orders/', order_views.place_order, name='place_order'),
    path('user/orders/details/', order_views.order_detail, name='order_detail'),
    path('user/orders/cancel-order/', order_views.cancel_order, name='cancel_order'),
    path('user/orders/cancel-order-item/', order_views.cancel_order_item_view, name='cancel_order_item'),
    path('user/orders/invoice/', order_views.download_invoice, name='download_invoice'),

    #RETURN
    path("user/return/request/",return_views.request_return,name="request_return"),
    path("user/return/status/", return_views.return_status_view, name="return_status_view"),
    path("user/return/detail/", return_views.return_detail_view, name="return_detail_view"),

    path("admin/return-list/", return_views.admin_return_list, name="admin_return_list"),
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