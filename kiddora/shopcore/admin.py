# shopcore/admin.py

from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone

from .models import (
    Coupon, Offer,
    Cart, CartItem,
    Order, OrderItem,
    Return,
    Review,
    Wishlist, WishlistItem,
    Banner,
)


# ═══════════════════════════════════════════════════════════════
#  COUPON
# ═══════════════════════════════════════════════════════════════

@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = (
        "code", "discount_type", "discount_value", "max_discount",
        "min_order_amount", "usage_limit", "used_count",
        "is_active", "is_deleted", "start_date", "expiry_date", "created_at",
    )
    list_filter   = ("discount_type", "is_active", "is_deleted")
    search_fields = ("code",)
    readonly_fields = ("used_count", "created_at")
    ordering = ("-created_at",)
    fieldsets = (
        ("Coupon Details", {
            "fields": ("code", "discount_type", "discount_value", "max_discount", "min_order_amount"),
        }),
        ("Validity", {
            "fields": ("start_date", "expiry_date", "usage_limit", "used_count"),
        }),
        ("Status", {
            "fields": ("is_active", "is_deleted"),
        }),
        ("Meta", {
            "classes": ("collapse",),
            "fields": ("created_at",),
        }),
    )


# ═══════════════════════════════════════════════════════════════
#  OFFER
# ═══════════════════════════════════════════════════════════════

@admin.register(Offer)
class OfferAdmin(admin.ModelAdmin):
    list_display = (
        "offer_type", "product", "category", "referral_coupon",
        "discount_percent", "start_date", "end_date",
        "is_active", "is_deleted", "created_at",
    )
    list_filter   = ("offer_type", "is_active", "is_deleted")
    search_fields = ("product__product_name", "category__category_name")
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)
    fieldsets = (
        ("Offer Target", {
            "fields": ("offer_type", "product", "category", "referral_coupon"),
        }),
        ("Discount", {
            "fields": ("discount_percent", "start_date", "end_date"),
        }),
        ("Status", {
            "fields": ("is_active", "is_deleted"),
        }),
        ("Meta", {
            "classes": ("collapse",),
            "fields": ("created_at",),
        }),
    )

# ═══════════════════════════════════════════════════════════════
#  CART
# ═══════════════════════════════════════════════════════════════

class CartItemInline(admin.TabularInline):
    model  = CartItem
    extra  = 0
    fields = ("variant", "quantity", "added_at")
    readonly_fields = ("added_at",)


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display  = ("user", "coupon", "item_count", "updated_at")
    search_fields = ("user__email",)
    readonly_fields = ("updated_at",)
    inlines = [CartItemInline]
    ordering = ("-updated_at",)

    @admin.display(description="Items")
    def item_count(self, obj):
        return obj.items.count()


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display  = ("cart", "variant", "quantity", "added_at")
    search_fields = ("cart__user__email", "variant__sku")
    readonly_fields = ("added_at",)
    ordering = ("-added_at",)


# ═══════════════════════════════════════════════════════════════
#  ORDER
# ═══════════════════════════════════════════════════════════════

class OrderItemInline(admin.TabularInline):
    model  = OrderItem
    extra  = 0
    fields = (
        "variant", "quantity", "unit_price",
        "discount_amount", "total_price", "item_status",
    )
    readonly_fields = (
        "variant", "quantity", "unit_price",
        "discount_amount", "total_price",
    )
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "order_id", "user", "order_status",
        "payment_method", "payment_status",
        "total_amount", "discount_amount", "coupon_discount",
        "shipping_charge", "final_amount", "order_date",
    )
    list_filter   = ("order_status", "payment_method", "payment_status")
    search_fields = ("order_id", "user__email")
    readonly_fields = (
        "order_id", "order_date", "updated_at",
        "delivered_at", "cancelled_at",
    )
    inlines = [OrderItemInline]
    ordering = ("-order_date",)
    fieldsets = (
        ("Order Info", {
            "fields": ("order_id", "user", "address", "order_date", "updated_at"),
        }),
        ("Status", {
            "fields": ("order_status", "payment_method", "payment_status"),
        }),
        ("Financials", {
            "fields": (
                "total_amount", "discount_amount",
                "coupon", "coupon_discount",
                "shipping_charge", "final_amount",
            ),
        }),
        ("Cancellation", {
            "classes": ("collapse",),
            "fields": ("delivered_at", "cancelled_at", "cancel_reason"),
        }),
    )


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display  = (
        "order", "variant", "quantity",
        "unit_price", "discount_amount", "total_price", "item_status",
    )
    list_filter   = ("item_status",)
    search_fields = ("order__order_id", "variant__sku")
    readonly_fields = ("total_price",)
    ordering = ("-order__order_date",)


# ═══════════════════════════════════════════════════════════════
#  RETURN
# ═══════════════════════════════════════════════════════════════

@admin.register(Return)
class ReturnAdmin(admin.ModelAdmin):
    list_display  = (
        "order_item", "status", "refund_amount",
        "reviewed_at", "refunded_at", "created_at",
    )
    list_filter   = ("status",)
    search_fields = ("order_item__order__order_id",)
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)
    fieldsets = (
        ("Return Details", {
            "fields": ("order_item", "reason", "status", "refund_amount", "admin_remark"),
        }),
        ("Timestamps", {
            "classes": ("collapse",),
            "fields": ("reviewed_at", "refunded_at", "created_at"),
        }),
    )


# ═══════════════════════════════════════════════════════════════
#  REVIEW
# ═══════════════════════════════════════════════════════════════

@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display  = ("user", "product", "rating", "is_approved", "created_at")
    list_filter   = ("rating", "is_approved")
    search_fields = ("user__email", "product__product_name")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-created_at",)
    actions = ["approve_reviews", "unapprove_reviews"]

    @admin.action(description="Approve selected reviews")
    def approve_reviews(self, request, queryset):
        updated = queryset.update(is_approved=True)
        self.message_user(request, f"{updated} review(s) approved.")

    @admin.action(description="Unapprove selected reviews")
    def unapprove_reviews(self, request, queryset):
        updated = queryset.update(is_approved=False)
        self.message_user(request, f"{updated} review(s) unapproved.")


# ═══════════════════════════════════════════════════════════════
#  WISHLIST
# ═══════════════════════════════════════════════════════════════

class WishlistItemInline(admin.TabularInline):
    model  = WishlistItem
    extra  = 0
    fields = ("product", "added_at")
    readonly_fields = ("added_at",)


@admin.register(Wishlist)
class WishlistAdmin(admin.ModelAdmin):
    list_display  = ("user", "item_count")
    search_fields = ("user__email",)
    inlines = [WishlistItemInline]

    @admin.display(description="Items")
    def item_count(self, obj):
        return obj.items.count()


# ═══════════════════════════════════════════════════════════════
#  BANNER
# ═══════════════════════════════════════════════════════════════

def _banner_image_preview(obj):
    if obj.image:
        return format_html(
            '<img src="{}" style="height:54px;width:96px;object-fit:cover;'
            'border-radius:6px;border:1px solid #eee;" />',
            obj.image.url,
        )
    return "—"
_banner_image_preview.short_description = "Preview"


def _banner_live_status(obj):
    if obj.is_live():
        return format_html(
            '<span style="color:#16a34a;font-weight:700;">&#10003; Live</span>'
        )
    return format_html(
        '<span style="color:#dc2626;font-weight:700;">&#10007; Off</span>'
    )
_banner_live_status.short_description = "Status"


@admin.action(description="Activate selected banners")
def activate_banners(modeladmin, request, queryset):
    updated = queryset.update(is_active=True)
    modeladmin.message_user(request, f"{updated} banner(s) activated.")


@admin.action(description="Deactivate selected banners")
def deactivate_banners(modeladmin, request, queryset):
    updated = queryset.update(is_active=False)
    modeladmin.message_user(request, f"{updated} banner(s) deactivated.")


@admin.register(Banner)
class BannerAdmin(admin.ModelAdmin):
    list_display  = (
        _banner_image_preview,
        "title", "slot", "display_order", "badge_text",
        "is_active", _banner_live_status,
        "start_date", "end_date", "created_at",
    )
    list_filter   = ("slot", "is_active")
    search_fields = ("title", "subtitle", "badge_text", "cta_text")
    list_editable = ("display_order", "is_active")
    ordering      = ("display_order", "-created_at")
    readonly_fields = ("created_at", _banner_image_preview)
    actions = (activate_banners, deactivate_banners)
    fieldsets = (
        ("Banner Content", {
            "fields": ("title", "subtitle", "image", _banner_image_preview, "badge_text"),
        }),
        ("Call to Action", {
            "fields": ("cta_text", "cta_url"),
        }),
        ("Display Settings", {
            "fields": ("slot", "display_order", "is_active"),
        }),
        ("Scheduling", {
            "classes": ("collapse",),
            "fields": ("start_date", "end_date"),
        }),
        ("Meta", {
            "classes": ("collapse",),
            "fields": ("created_at",),
        }),
    )