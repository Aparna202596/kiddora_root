from django.urls import path
from products.views import catalog_views 
from products.views import product_views
from products.views import search_views
app_name = "products"

urlpatterns = [
    path("categories/", catalog_views.category_list_view, name="category_list"),
    path("categories/<int:category_id>/subcategories/", catalog_views.subcategory_list_view, name="subcategory_list"),

    path("subcategory/<int:subcategory_id>/", product_views.product_list_view, name="product_list_by_subcategory"),
    path("products/", product_views.product_list, name="product_list"),
    path("products/<int:product_id>/", product_views.product_detail_view, name="product_detail"),
    path("ajax/variant-info/", product_views.ajax_variant_info, name="ajax_variant_info"),

    path("search/", search_views.search_products, name="product_search"),
    path("subcategory/<int:subcategory_id>/", product_views.product_list, name="product_list_by_subcategory"),
]