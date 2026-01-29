from django.urls import path
from products.views import catalog_views 
from products.views import coupon_views
from products.views import offer_views
from products.views import product_admin 
from products.views import product_views
from products.views import search_views
app_name = "products"

urlpatterns = [
    #calatog views
    path("user/categories/", catalog_views.category_list_view, name="category_list"),
    path("user/categories/subcategories/", catalog_views.subcategory_list_view, name="subcategory_list"),

    #Coupon_views
    path("admin/coupon/", coupon_views.admin_coupon_list, name="admin_coupon_list"),
    path("admin/coupon/create_coupon/", coupon_views.admin_create_coupon, name="admin_create_coupon"),
    path("admin/coupon/delete_coupon/", coupon_views.admin_delete_coupon, name="admin_delete_coupon"),

    path("coupon/apply/", coupon_views.apply_coupon, name="apply_coupon"),
    path("coupon/remove/", coupon_views.remove_coupon, name="remove_coupon"),
    path("coupon/coupon_list/",coupon_views.available_coupons, name="available_coupons"),

    #Offer_views
    path("admin/offer_list/", offer_views.admin_offer_list, name="admin_offer_list"),
    path("admin/product_offer/", offer_views.admin_product_offer, name="admin_product_offer"),
    path("admin/category_offer/", offer_views.admin_category_offer, name="admin_category_offer"),
    path("admin/referral_offer/", offer_views.admin_referral_offer, name="admin_referral_offer"),
    path("admin/remove_offer/<int:offer_id>/", offer_views.admin_remove_offer, name="admin_remove_offer"),

    path("products/offer/best_offer", offer_views.get_best_offer_for_product, name="get_best_offer_for_product"),
    path("products/offer/calculate_offer_price", offer_views.calculate_offer_price, name="calculate_offer_price"),
    path("products/offer/calculate_cart_total", offer_views.calculate_cart_total, name="calculate_cart_total"),
    path("products/offer/apply_coupon_to_total", offer_views.apply_coupon_to_total, name="apply_coupon_to_total"),
    path("products/offer/checkout_total", offer_views.calculate_checkout_total, name="calculate_checkout_total"),

    #Product_views
    path("subcategory/products/", product_views.product_list, name="product_list"),
    path("products/", product_views.product_detail_view, name="product_detail"),
    path("products/variant-info/", product_views.ajax_variant_info, name="ajax_variant_info"),

    #Product_admin
    path("admin/category/", product_admin.admin_category_list, name="admin_category_list"),
    path("admin/category/add/", product_admin.admin_add_category, name="admin_add_category"),
    path("admin/category/edit/", product_admin.admin_edit_category, name="admin_edit_category"),
    path("admin/category/delete/", product_admin.admin_delete_category, name="admin_delete_category"),

    path("admin/inventory/",product_admin.admin_inventory_list, name="admin_inventory_list"),
    path("admin/inventory/update/",product_admin.admin_update_stock, name="admin_update_stock"),

    path("admin/category/products/", product_admin.admin_product_list, name="admin_product_list"),
    path("admin/category/products/add/", product_admin.admin_add_product, name="admin_add_product"),
    path("admin/category/products/edit/", product_admin.admin_edit_product, name="admin_edit_product"),
    path("admin/category/products/delete/", product_admin.admin_delete_product, name="admin_delete_product"),


    #search_views
    path("user/search/", search_views.search_products, name="product_search"),
]