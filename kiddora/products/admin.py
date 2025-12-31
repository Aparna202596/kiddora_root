from django.contrib import admin
from .models import Category, SubCategory, Product, ProductVariant, Inventory


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("category_name", "is_active")
    search_fields = ("category_name",)


@admin.register(SubCategory)
class SubCategoryAdmin(admin.ModelAdmin):
    list_display = ("subcategory_name", "category")
    search_fields = ("subcategory_name",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "product_name", "brand", "final_price",
        "sku", "is_active"
    )
    search_fields = ("product_name", "sku")
    list_filter = ("brand", "is_active")


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ("product", "color", "size", "barcode", "is_active")
    search_fields = ("barcode",)


@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = (
        "variant",
        "quantity_available",
        "quantity_reserved",
        "updated_at"
    )

