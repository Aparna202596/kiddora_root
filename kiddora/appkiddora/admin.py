from django.contrib import admin
from .models import *

# CART 
@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("user", "updated_at")

@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ("cart", "variant", "quantity")

#ORDER
class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("unit_price", "total_price")

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "id", "user", "order_status",
        "payment_status", "final_amount", "order_date"
    )
    list_filter = ("order_status", "payment_status")
    inlines = [OrderItemInline]
    ordering = ("-order_date",)
    
#RETURN
@admin.register(Return)
class ReturnAdmin(admin.ModelAdmin):
    list_display = ("order", "product", "status", "created_at")
    list_filter = ("status",)

#REVIEW
@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("user", "product", "rating")
    list_filter = ("rating",)

#WALLET
@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ("user", "balance")

@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display = ("wallet", "txn_type", "amount", "reference_type","reference_id","created_at")

@admin.register(Wishlist)
class WishlistAdmin(admin.ModelAdmin):
    list_display = ("user",)


@admin.register(WishlistItem)
class WishlistItemAdmin(admin.ModelAdmin):
    list_display = ("wishlist", "product")