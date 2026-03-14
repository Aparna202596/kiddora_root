from django.contrib import admin
from .models import Payment, PaymentLog, Wallet, WalletTransaction


# PAYMENT LOG INLINE

class PaymentLogInline(admin.TabularInline):
    model = PaymentLog
    extra = 0

    fields = (
        "log_id",
        "gateway",
        "event_type",
        "gateway_event_id",
        "created_at",
    )

    readonly_fields = (
        "log_id",
        "gateway",
        "event_type",
        "gateway_event_id",
        "created_at",
    )

    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


# PAYMENT ADMIN

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):

    list_display = (
        "txn_id",
        "order",
        "payment_method",
        "payment_status",
        "amount",
        "retry_count",
        "initiated_at",
        "completed_at",
        "created_at",
    )

    list_filter = (
        "payment_method",
        "payment_status",
    )

    search_fields = (
        "txn_id",
        "order__order_id",
        "paypal_order_id",
        "paypal_capture_id",
    )

    readonly_fields = (
        "txn_id",
        "created_at",
        "updated_at",
        "initiated_at",
        "completed_at",
        "paypal_order_id",
        "paypal_capture_id",
    )

    inlines = [PaymentLogInline]

    ordering = ("-created_at",)


# PAYMENT LOG ADMIN

@admin.register(PaymentLog)
class PaymentLogAdmin(admin.ModelAdmin):

    list_display = (
        "log_id",
        "payment",
        "gateway",
        "event_type",
        "gateway_event_id",
        "created_at",
    )

    list_filter = (
        "gateway",
        "event_type",
    )

    search_fields = (
        "gateway_event_id",
        "payment__txn_id",
    )

    readonly_fields = (
        "log_id",
        "payload",
        "created_at",
    )

    ordering = ("-created_at",)


# WALLET ADMIN

@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):

    list_display = (
        "user",
        "balance",
        "created_at",
        "updated_at",
    )

    search_fields = (
        "user__email",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )


# WALLET TRANSACTION ADMIN

@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):

    list_display = (
        "wallet",
        "txn_type",
        "amount",
        "order",
        "created_at",
    )

    list_filter = (
        "txn_type",
    )

    search_fields = (
        "wallet__user__email",
        "order__order_id",
    )

    readonly_fields = (
        "created_at",
    )

    ordering = ("-created_at",)