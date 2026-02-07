from django.contrib import admin
from .models import Category, SubCategory, Product, ProductVariant, Inventory, ProductImage

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("category_name", "is_active")
    search_fields = ("category_name",)
    list_filter = ("is_active",)

@admin.register(SubCategory)
class SubCategoryAdmin(admin.ModelAdmin):
    list_display = ("subcategory_name", "category")
    search_fields = ("subcategory_name",)
    list_filter = ("category",)

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("product_name", "brand", "fabric", "gender", "final_price", "sku", "is_active")
    search_fields = ("product_name", "sku", "brand", "about_product")
    list_filter = ("brand", "fabric", "gender", "is_active")
    ordering = ("product_name",)
    readonly_fields = ("sku", "final_price")
    fieldsets = (
        ("Basic Information", {
            "fields": ("subcategory", "product_name", "brand")
        }),
        ("Target Group", {
            "fields": ("gender", "fabric")
        }),
        ("Pricing", {
            "fields": ("base_price", "discount_percent", "final_price")
        }),
        ("Inventory & Status", {
            "fields": ("stock", "is_active")
        }),
        ("Description", {
            "fields": ("about_product",)
        }),
        ("System", {
            "fields": ("sku",)
        }),
    )
    inlines = [
        admin.TabularInline(model=ProductImage, extra=1),
    ]

@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ("product", "color", "size", "barcode", "is_active")
    search_fields = ("barcode", "product__product_name")
    list_filter = ("size", "is_active")

@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = ("variant", "quantity_available", "quantity_reserved", "quantity_sold", "updated_at")
    search_fields = ("variant__barcode", "variant__product__product_name")
    list_filter = ("updated_at",)
    readonly_fields = ("updated_at",)
    autocomplete_fields = ("variant",)
