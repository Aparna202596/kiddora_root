from django.contrib import admin
from .models import (
    Coupon, Offer,
    ReferralCode, ReferralUse,
    Cart, CartItem,
    Order, OrderItem,
    Return,
    Review,
    Wallet, WalletTransaction,
    Wishlist, WishlistItem,
)
#  COUPON
@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display  = (
        "code", "discount_type", "discount_value",
        "min_order_amount", "usage_limit", "used_count",
        "is_active", "start_date", "expiry_date", "created_at",
    )
    list_filter = ("discount_type", "is_active", "is_deleted")
    search_fields = ("code",)
    readonly_fields = ("used_count", "created_at")
    ordering = ("-created_at",)

#  OFFER
@admin.register(Offer)
class OfferAdmin(admin.ModelAdmin):
    list_display  = (
        "offer_type", "product", "category",
        "discount_percent", "start_date", "end_date",
        "is_active", "is_deleted", "created_at",
    )
    list_filter = ("offer_type", "is_active", "is_deleted")
    search_fields = ("product__product_name", "category__category_name")
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)

#  REFERRAL
@admin.register(ReferralCode)
class ReferralCodeAdmin(admin.ModelAdmin):
    list_display = ("user", "code", "created_at")
    search_fields = ("user__email", "code")
    readonly_fields = ("code", "created_at")
    ordering = ("-created_at",)


@admin.register(ReferralUse)
class ReferralUseAdmin(admin.ModelAdmin):
    list_display = ("referral_code", "referred_user", "coupon_awarded", "created_at")
    search_fields = ("referral_code__user__email", "referred_user__email")
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)

#  CART
class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    fields = ("variant", "quantity", "added_at")
    readonly_fields = ("added_at",)

@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("user", "coupon", "updated_at")
    search_fields = ("user__email",)
    readonly_fields = ("updated_at",)
    inlines = [CartItemInline]
    ordering = ("-updated_at",)

#  ORDER
class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
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
    list_display    = (
        "order_id", "user", "order_status",
        "payment_method", "payment_status",
        "total_amount", "discount_amount", "coupon_discount",
        "shipping_charge", "final_amount", "order_date",
    )
    list_filter = ("order_status", "payment_method", "payment_status")
    search_fields = ("order_id", "user__email")
    readonly_fields = (
        "order_id", "order_date", "updated_at",
        "delivered_at", "cancelled_at",
    )
    inlines = [OrderItemInline]
    ordering = ("-order_date",)


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = (
        "order", "variant", "quantity",
        "unit_price", "discount_amount", "total_price", "item_status",
    )
    list_filter = ("item_status",)
    search_fields = ("order__order_id", "variant__sku")
    readonly_fields = ("total_price",)
    ordering = ("-order__order_date",)

#  RETURN
@admin.register(Return)
class ReturnAdmin(admin.ModelAdmin):
    list_display    = (
        "order_item", "status", "refund_amount",
        "reviewed_at", "refunded_at", "created_at",
    )
    list_filter = ("status",)
    search_fields = ("order_item__order__order_id",)
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)

#  REVIEW
@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = (
        "user", "product", "rating",
        "is_approved", "created_at",
    )
    list_filter = ("rating", "is_approved")
    search_fields = ("user__email", "product__product_name")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-created_at",)

#  WALLET
class WalletTransactionInline(admin.TabularInline):
    model = WalletTransaction
    extra = 0
    fields = (
        "txn_id", "txn_type", "amount",
        "balance_after", "reference_type", "reference_id",
        "description", "created_at",
    )
    readonly_fields = (
        "txn_id", "txn_type", "amount",
        "balance_after", "reference_type", "reference_id",
        "description", "created_at",
    )
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ("user", "balance", "created_at", "updated_at")
    search_fields = ("user__email",)
    readonly_fields = ("created_at", "updated_at")
    inlines = [WalletTransactionInline]
    ordering = ("-created_at",)


@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "txn_id", "wallet", "txn_type",
        "amount", "balance_after",
        "reference_type", "reference_id",
        "description", "created_at",
    )
    list_filter = ("txn_type", "reference_type")
    search_fields = ("wallet__user__email", "reference_id")
    readonly_fields = ("txn_id", "created_at")
    ordering = ("-created_at",)

#  WISHLIST
class WishlistItemInline(admin.TabularInline):
    model = WishlistItem
    extra = 0
    fields = ("product", "added_at")
    readonly_fields = ("added_at",)


@admin.register(Wishlist)
class WishlistAdmin(admin.ModelAdmin):
    list_display = ("user", "item_count")
    search_fields = ("user__email",)
    inlines = [WishlistItemInline]

    @admin.display(description="Items")
    def item_count(self, obj):
        return obj.items.count()