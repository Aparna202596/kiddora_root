from django.urls import path
from products.views import catalog_views 
from products.views import coupon_views
from products.views import offer_views
from products.views import category_admin_views 
from products.views import product_admin_views 
from products.views import inventory_stock_views 
from products.views import search_views
app_name = "products"

urlpatterns = [
    #calatog views
    path("user/categories/", catalog_views.category_list_view, name="category_list"),
    path("user/categories/<int:category_id>/subcategories/",catalog_views.subcategory_list_view,name="subcategory_list"),
    path("user/products/",catalog_views.product_list,name="product_list"),
    path("user/categories/<int:category_id>/subcategory/<int:subcategory_id>/products/<int:product_id>/",catalog_views.product_detail_view,name="product_detail"),
    path("user/categories/<int:category_id>/subcategory/<int:subcategory_id>/products/<int:product_id>/variant-info/",catalog_views.ajax_variant_info,name="ajax_variant_info"),

    #Admin coupon management views
    path("admin/coupon/", coupon_views.admin_coupon_list, name="admin_coupon_list"),
    path("admin/coupon/create_coupon/", coupon_views.admin_create_coupon, name="admin_create_coupon"),
    path("admin/coupon/delete_coupon/", coupon_views.admin_delete_coupon, name="admin_delete_coupon"),
    # User-facing coupon endpoints
    path("coupon/apply/", coupon_views.apply_coupon, name="apply_coupon"),
    path("coupon/remove/", coupon_views.remove_coupon, name="remove_coupon"),
    path("coupon/coupon_list/",coupon_views.available_coupons, name="available_coupons"),

    #Admin offer management views
    path("admin/offer_list/", offer_views.admin_offer_list, name="admin_offer_list"),
    path("admin/product_offer/", offer_views.admin_product_offer, name="admin_product_offer"),
    path("admin/category_offer/", offer_views.admin_category_offer, name="admin_category_offer"),
    path("admin/referral_offer/", offer_views.admin_referral_offer, name="admin_referral_offer"),
    path("admin/remove_offer/<int:offer_id>/", offer_views.admin_remove_offer, name="admin_remove_offer"),
    # User-facing offer endpoints 
    path("products/offer/best_offer", offer_views.get_best_offer_for_product, name="get_best_offer_for_product"),
    path("products/offer/calculate_offer_price", offer_views.calculate_offer_price, name="calculate_offer_price"),
    path("products/offer/calculate_cart_total", offer_views.calculate_cart_total, name="calculate_cart_total"),
    path("products/offer/apply_coupon_to_total", offer_views.apply_coupon_to_total, name="apply_coupon_to_total"),
    path("products/offer/checkout_total", offer_views.calculate_checkout_total, name="calculate_checkout_total"),

    #Product_admin
    # Category
    path("admin/category/", category_admin_views.admin_category_list, name="admin_category_list"),
    path("admin/category/add/", category_admin_views.admin_add_category, name="admin_add_category"),
    path("admin/category/edit/<int:category_id>/", category_admin_views.admin_edit_category, name="admin_edit_category"),
    path("admin/category/delete/<int:category_id>/", category_admin_views.admin_delete_category, name="admin_delete_category"),

    # SubCategory
    path("admin/category/subcategories/", category_admin_views.admin_subcategory_list, name="admin_subcategory_list"),
    path("admin/category/subcategories/add/", category_admin_views.admin_add_subcategory, name="admin_add_subcategory"),
    path("admin/category/subcategories/edit/<int:subcategory_id>/", category_admin_views.admin_edit_subcategory, name="admin_edit_subcategory"),
    path("admin/category/subcategories/delete/<int:subcategory_id>/", category_admin_views.admin_delete_subcategory, name="admin_delete_subcategory"),
    
    # Product
    path("admin/category/subcategories/products/", product_admin_views.admin_product_list, name="admin_product_list"),
    path("admin/category/subcategories/products/add/", product_admin_views.admin_add_product, name="admin_add_product"),
    path("admin/category/subcategories/products/edit/<int:product_id>/", product_admin_views.admin_edit_product, name="admin_edit_product"),
    path("admin/category/subcategories/products/delete/<int:product_id>/", product_admin_views.admin_delete_product, name="admin_delete_product"),
    path("admin/category/subcategories/products/<int:product_id>/",product_admin_views.admin_product_details,name="admin_product_details"),

    # Inventory
    path("admin/inventory/",inventory_stock_views.admin_inventory_list, name="admin_inventory_list"),
    path('admin/inventory/update/', inventory_stock_views.admin_update_stock, name='admin_update_stock'),

    #search_views
    path("user/search/", search_views.search_products, name="product_search"),
]