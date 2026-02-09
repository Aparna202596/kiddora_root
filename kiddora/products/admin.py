from django.contrib import admin
from .models import *


# @admin.register(Category)
# class CategoryAdmin(admin.ModelAdmin):
#     list_display = ("category_name", "is_active")
#     search_fields = ("category_name",)
#     list_filter = ("is_active",)


# @admin.register(SubCategory)
# class SubCategoryAdmin(admin.ModelAdmin):
#     list_display = ("subcategory_name", "category")
#     search_fields = ("subcategory_name",)
#     list_filter = ("category",)

# ---------- INLINE ----------
class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1


class InventoryInline(admin.StackedInline):
    model = Inventory
    extra = 0


# ---------- PRODUCT ----------
@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("product_name", "brand", "final_price", "stock", "is_active")
    list_filter = ("is_active", "gender", "fabric", "subcategory")
    search_fields = ("product_name", "brand", "sku")
    inlines = [ProductImageInline]


# ---------- PRODUCT VARIANT ----------
@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ("product", "barcode", "is_active")
    list_filter = ("is_active",)
    search_fields = ("barcode", "product__product_name")
    filter_horizontal = ("ages", "colors")
    inlines = [InventoryInline]


# ---------- BASIC MODELS ----------
admin.site.register(Category)
admin.site.register(SubCategory)
admin.site.register(AgeGroup)
admin.site.register(Color)
admin.site.register(ProductImage)
admin.site.register(Inventory)
admin.site.register(Coupon)
admin.site.register(Offer)
