from django.contrib import admin
from django.db.models import Sum
from .models import *

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):

    list_display = ("category_name", "is_active")
    search_fields = ("category_name",)
    list_filter = ("is_active",)
    ordering = ("-id",)
    list_per_page = 20
    actions = ["soft_delete", "restore_category"]

    def soft_delete(self, request, queryset):
        queryset.update(is_active=False)
    soft_delete.short_description = "Soft delete selected categories"

    def restore_category(self, request, queryset):
        queryset.update(is_active=True)
    restore_category.short_description = "Restore selected categories"

@admin.register(SubCategory)
class SubCategoryAdmin(admin.ModelAdmin):

    list_display = ("subcategory_name", "category")
    search_fields = ("subcategory_name", "category__category_name")
    list_filter = ("category",)
    ordering = ("-id",)
    list_per_page = 20


class ProductImageInline(admin.StackedInline):
    model = ProductImage
    extra = 1

class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1
    show_change_link = True

class InventoryInline(admin.StackedInline):
    model = Inventory
    extra = 0

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):

    list_display = (
        "product_name",
        "subcategory",
        "brand",
        "base_price",
        "final_price",
        "is_active",
        "total_stock",
    )

    search_fields = (
        "product_name",
        "brand",
        "subcategory__subcategory_name",
        "subcategory__category__category_name",
    )

    list_filter = (
        "is_active",
        "gender",
        "fabric",
        "subcategory__category",
        "subcategory",
    )

    ordering = ("-id",)
    list_per_page = 20

    inlines = [
        ProductVariantInline,
        ProductImageInline,
    ]

    actions = ["soft_delete", "restore_product"]

    def total_stock(self, obj):
        return (
            Inventory.objects.filter(variant__product=obj)
            .aggregate(total=Sum("quantity_available"))["total"]
            or 0
        )
    total_stock.short_description = "Stock"

    def soft_delete(self, request, queryset):
        queryset.update(is_active=False)
    soft_delete.short_description = "Soft delete selected products"

    def restore_product(self, request, queryset):
        queryset.update(is_active=True)
    restore_product.short_description = "Restore selected products"

@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):

    list_display = (
        "product",
        "color",
        "age_group",
        "sku",
        "barcode",
        "is_active",
        "stock",
    )

    search_fields = (
        "product__product_name",
        "sku",
        "barcode",
    )

    list_filter = (
        "color",
        "age_group",
        "is_active",
    )

    ordering = ("-id",)
    list_per_page = 20

    inlines = [InventoryInline]

    def stock(self, obj):
        return getattr(obj.inventory, "quantity_available", 0)
    
@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):

    list_display = ("product", "is_default")
    search_fields = ("product__product_name",)
    list_filter = ("is_default",)

@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):

    list_display = (
        "variant",
        "quantity_available",
        "quantity_reserved",
        "quantity_sold",
        "updated_at",
    )

    search_fields = ("variant__product__product_name", "variant__sku")
    list_filter = ("updated_at",)
    ordering = ("-updated_at",)
    list_per_page = 20

@admin.register(Color)
class ColorAdmin(admin.ModelAdmin):
    search_fields = ("color",)
    ordering = ("color",)

@admin.register(AgeGroup)
class AgeGroupAdmin(admin.ModelAdmin):
    search_fields = ("age",)
    ordering = ("age",)