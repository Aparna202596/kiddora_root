from django import views
from django.urls import path
from shopcore.views import (cart_views, checkout_views, coupon_views,
                            offer_views, order_views, referral_views,
                            return_views, review_views, store_views,
                            wishlist_views)

app_name = "shopcore"

urlpatterns = [
    # ────────────────────────────────────────── HOME (public) ─────────────────────────────────────────────────────────
    path("user/home/", store_views.home, name="home"),
    path("", store_views.anonymous_home, name="anonymous_home"),

    # ────────────────────────────────────────── STORE (public) ────────────────────────────────────────────────────────
    path("aboutus/", store_views.aboutus_view, name="about_us"),
    path("contactus/", store_views.contactus_view, name="contact_us"),
    path("privacy-policy/", store_views.privacy_policy_view, name="privacy_policy"),
    path("return-policy/", store_views.return_policy_view, name="return_policy"),
    path("cookie-policy/", store_views.cookie_policy_view, name="cookie_policy"),
    path("blog/", store_views.blog_view, name="blog"),
    path(
        "terms-conditions/", store_views.terms_conditions_view, name="terms_conditions"
    ),
    path("user/size-chart/", store_views.size_chart, name="size_chart"),

    # ────────────────────────────────────────── BANNER — ADMIN ────────────────────────────────────────────────────────
    path("admin/banners/", store_views.admin_banner_list, name="admin_banner_list"),
    path("admin/banners/add/", store_views.admin_add_banner, name="admin_add_banner"),
    path(
        "admin/banners/<int:banner_id>/edit/",
        store_views.admin_edit_banner,
        name="admin_edit_banner",
    ),
    path(
        "admin/banners/block/<int:banner_id>/",
        store_views.admin_block_banner,
        name="admin_block_banner",
    ),
    path(
        "admin/banners/unblock/<int:banner_id>/",
        store_views.admin_unblock_banner,
        name="admin_unblock_banner",
    ),
    path(
        "admin/banners/<int:banner_id>/delete/",
        store_views.admin_delete_banner,
        name="admin_delete_banner",
    ),
    # ────────────────────────────────────────── CART — USER ───────────────────────────────────────────────────────────
    path("cart/", cart_views.cart_view, name="cart"),
    path("cart/add/<int:variant_id>/", cart_views.add_to_cart, name="add_to_cart"),
    path(
        "cart/remove/<int:item_id>/",
        cart_views.remove_from_cart,
        name="remove_from_cart",
    ),
    path(
        "cart/update/<int:item_id>/",
        cart_views.update_cart_quantity,
        name="update_cart_quantity",
    ),
    path("cart/clear/", cart_views.clear_cart, name="clear_cart"),
    # ────────────────────────────────────────── WISHLIST — USER ───────────────────────────────────────────────────────
    path("wishlist/", wishlist_views.wishlist_view, name="wishlist"),
    path(
        "wishlist/toggle/<int:product_id>/",
        cart_views.toggle_wishlist,
        name="toggle_wishlist",
    ),
    path(
        "wishlist/remove/<int:product_id>/",
        wishlist_views.remove_from_wishlist,
        name="remove_from_wishlist",
    ),
    path(
        "wishlist/move-to-cart/<int:variant_id>/",
        wishlist_views.move_to_cart,
        name="move_to_cart",
    ),
    path(
        "wishlist/variant-popup/<int:product_id>/",
        wishlist_views.wishlist_variant_popup,
        name="wishlist_variant_popup",
    ),
    # ────────────────────────────────────────── CHECKOUT — USER ───────────────────────────────────────────────────────
    path("checkout/", checkout_views.checkout, name="checkout"),
    path("checkout/place-order/", checkout_views.place_order, name="place_order"),
    path(
        "checkout/address/save/",
        checkout_views.save_new_address,
        name="save_new_address",
    ),
    path(
        "checkout/address/edit/<int:address_id>/",
        checkout_views.edit_address,
        name="edit_address",
    ),
    path(
        "order/success/<str:order_id>/",
        checkout_views.order_success,
        name="order_success",
    ),
    # ────────────────────────────────────────── ORDER MANAGEMENT — USER ───────────────────────────────────────────────
    path("orders/", order_views.user_order_list, name="user_order_list"),
    path(
        "orders/<str:order_id>/",
        order_views.user_order_detail,
        name="user_order_detail",
    ),
    path(
        "orders/<str:order_id>/cancel/", order_views.cancel_order, name="cancel_order"
    ),
    path(
        "orders/<str:order_id>/cancel-item/<int:item_id>/",
        order_views.cancel_order_item,
        name="cancel_order_item",
    ),
    path(
        "orders/<str:order_id>/return-item/<int:item_id>/",
        order_views.request_return,
        name="request_return",
    ),
    path(
        "orders/<str:order_id>/invoice/",
        order_views.download_invoice,
        name="download_invoice",
    ),
    # ────────────────────────────────────────── ORDER MANAGEMENT — ADMIN ──────────────────────────────────────────────
    path("admin/orders/", order_views.admin_order_list, name="admin_order_list"),
    path(
        "admin/orders/<str:order_id>/",
        order_views.admin_order_detail,
        name="admin_order_detail",
    ),
    path(
        "admin/orders/<str:order_id>/update-status/",
        order_views.admin_update_order_status,
        name="admin_update_order_status",
    ),
    path(
        "admin/orders/<str:order_id>/item/<int:item_id>/update-status/",
        order_views.admin_update_item_status,
        name="admin_update_item_status",
    ),
    path(
        "admin/returns/<int:return_id>/handle/",
        order_views.admin_handle_return,
        name="admin_handle_return",
    ),
    # ────────────────────────────────────────── COUPON — USER ─────────────────────────────────────────────────────────
    path("user/checkout/coupon/apply/", coupon_views.apply_coupon, name="apply_coupon"),
    path(
        "user/checkout/coupon/remove/", coupon_views.remove_coupon, name="remove_coupon"
    ),
    path("user/coupons/", coupon_views.user_coupon_list, name="user_coupon_list"),
    # ────────────────────────────────────────── COUPON — ADMIN ────────────────────────────────────────────────────────
    path("admin/coupons/", coupon_views.admin_coupon_list, name="admin_coupon_list"),
    path("admin/coupons/add/", coupon_views.admin_add_coupon, name="admin_add_coupon"),
    path(
        "admin/coupons/<int:coupon_id>/",
        coupon_views.admin_coupon_detail,
        name="admin_coupon_detail",
    ),
    path(
        "admin/coupons/<int:coupon_id>/edit/",
        coupon_views.admin_edit_coupon,
        name="admin_edit_coupon",
    ),
    path(
        "admin/coupons/<int:coupon_id>/delete/",
        coupon_views.admin_delete_coupon,
        name="admin_delete_coupon",
    ),
    path(
        "admin/coupons/<int:coupon_id>/block/",
        coupon_views.admin_block_coupon,
        name="admin_block_coupon",
    ),
    path(
        "admin/coupons/<int:coupon_id>/unblock/",
        coupon_views.admin_unblock_coupon,
        name="admin_unblock_coupon",
    ),
    # ────────────────────────────────────────── OFFER — ADMIN ─────────────────────────────────────────────────────────
    path("admin/offers/", offer_views.admin_offer_list, name="admin_offer_list"),
    path("admin/offers/add/", offer_views.admin_add_offer, name="admin_add_offer"),
    path(
        "admin/offers/<int:offer_id>/edit/",
        offer_views.admin_edit_offer,
        name="admin_edit_offer",
    ),
    path(
        "admin/offers/<int:offer_id>/delete/",
        offer_views.admin_delete_offer,
        name="admin_delete_offer",
    ),
    path(
        "admin/offers/<int:offer_id>/block/",
        offer_views.admin_block_offer,
        name="admin_block_offer",
    ),
    path(
        "admin/offers/<int:offer_id>/unblock/",
        offer_views.admin_unblock_offer,
        name="admin_unblock_offer",
    ),
    # ────────────────────────────────────────── REFERRALS — USER ──────────────────────────────────────
    path("user/my-referrals/", referral_views.my_referrals, name="my_referrals"),
    # ────────────────────────────────────────── REFERRALS — ADMIN ─────────────────────────────────────
    path(
        "admin/referrals/",
        referral_views.admin_referral_list,
        name="admin_referral_list",
    ),
    path(
        "admin/referrals/<int:referral_id>/uses/",
        referral_views.admin_referral_uses,
        name="admin_referral_uses",
    ),
    # ────────────────────────────────────────── RETURN REQUESTS — USER ────────────────────────────────────────────────
    path(
        "orders/<str:order_id>/return/<int:item_id>/",
        return_views.request_return,
        name="request_return",
    ),
    # ────────────────────────────────────────── RETURN MANAGEMENT — ADMIN ─────────────────────────────────────────────
    path("admin/returns/", return_views.admin_return_list, name="admin_return_list"),
    path(
        "admin/returns/<int:return_id>/",
        return_views.admin_return_detail,
        name="admin_return_detail",
    ),
    path(
        "admin/returns/<int:return_id>/approve/",
        return_views.admin_approve_return,
        name="admin_approve_return",
    ),
    path(
        "admin/returns/<int:return_id>/reject/",
        return_views.admin_reject_return,
        name="admin_reject_return",
    ),
    path(
        "admin/returns/<int:return_id>/process-refund/",
        return_views.admin_process_refund,
        name="admin_process_refund",
    ),
    # ────────────────────────────────────────── REVIEWS — USER ────────────────────────────────────────────────────────

    path(
        "user/products/<int:product_id>/reviews/",
        review_views.my_reviews,
        name="my_reviews",
    ),
    path(
        "user/products/<int:product_id>/reviews/submit/",
        review_views.submit_review,
        name="submit_review",
    ),
    path(
        "user/products/<int:product_id>/reviews/delete/<int:review_id>/",
        review_views.delete_review,
        name="delete_review",
    ),
    # ────────────────────────────────────────── REVIEW MANAGEMENT — ADMIN ─────────────────────────────────────────────
    path("admin/reviews/", review_views.admin_review_list, name="admin_review_list"),
    path(
        "admin/reviews/<int:review_id>/approve/",
        review_views.admin_approve_review,
        name="admin_approve_review",
    ),
    path(
        "admin/reviews/<int:review_id>/reject/",
        review_views.admin_reject_review,
        name="admin_reject_review",
    ),
]
