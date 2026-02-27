from django.urls import path
from products.views import catalog_views 
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
    
    # PRODUCT MANAGEMENT
    path("admin/products/", product_admin_views.admin_product_list, name="admin_product_list"),
    path("admin/products/<int:product_id>/details/",product_admin_views.admin_product_details,name="admin_product_details"),
    
    path("admin/products/add/", product_admin_views.admin_add_product, name="admin_add_product"),
    path("admin/products/<int:product_id>/edit/", product_admin_views.admin_edit_product, name="admin_edit_product"),
    path("admin/products/<int:product_id>/delete/", product_admin_views.admin_delete_product, name="admin_delete_product"),

    path("admin/products/<int:product_id>/variants/add",product_admin_views.admin_add_variant,name="admin_add_variants"),

    # VARIANTS
    path("admin/products/<int:product_id>/variant/add/", product_admin_views.admin_add_variant, name="admin_add_variant"),
    path("admin/products/<int:product_id>/variant/<int:variant_id>/edit/", product_admin_views.admin_edit_variant, name="admin_edit_variant"),
    path("admin/products/<int:product_id>/variant/<int:variant_id>/delete/", product_admin_views.admin_delete_variant, name="admin_delete_variant"),

    # INVENTORY
    path("admin/inventory/", inventory_stock_views.admin_inventory_list, name="admin_inventory_list"),
    path("admin/inventory/<int:inventory_id>/update/", inventory_stock_views.update_stock, name="update_stock"),

    #search_views
    path("user/search/", search_views.search_products, name="product_search"),
]