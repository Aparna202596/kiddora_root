from django.contrib import admin
from payments.models import Payment, Wallet, WalletTransaction, PaymentLog


# ─────────────────────────────────────────────────────────────
# PAYMENT
# ─────────────────────────────────────────────────────────────

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display  = (
        "txn_id_display", "order", "payment_method",
        "payment_status", "amount", "initiated_at", "completed_at",
    )
    list_filter   = ("payment_method", "payment_status")
    search_fields = (
        "txn_id", "order__order_id",
        "paypal_order_id", "paypal_capture_id", "paypal_payer_email",
    )
    readonly_fields = (
        "txn_id", "txn_id_display",
        "paypal_order_id", "paypal_capture_id",
        "paypal_payer_id", "paypal_payer_email",
        "initiated_at", "completed_at", "created_at", "updated_at",
    )
    ordering = ("-created_at",)

    fieldsets = (
        ("Core", {
            "fields": ("txn_id", "order", "payment_method", "payment_status", "amount"),
        }),
        ("PayPal Details", {
            "fields": (
                "paypal_order_id", "paypal_capture_id",
                "paypal_payer_id", "paypal_payer_email",
            ),
            "classes": ("collapse",),
        }),
        ("Failure", {
            "fields": ("failure_reason",),
            "classes": ("collapse",),
        }),
        ("Timestamps", {
            "fields": ("initiated_at", "completed_at", "created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )


# ─────────────────────────────────────────────────────────────
# WALLET
# ─────────────────────────────────────────────────────────────

@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display  = ("user", "balance", "created_at", "updated_at")
    search_fields = ("user__email", "user__full_name")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-updated_at",)


# ─────────────────────────────────────────────────────────────
# WALLET TRANSACTION
# ─────────────────────────────────────────────────────────────

@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display  = (
        "txn_id_display", "get_user", "txn_type",
        "amount", "balance_after", "reference_type", "reference_id", "created_at",
    )
    list_filter   = ("txn_type", "reference_type")
    search_fields = (
        "txn_id", "wallet__user__email",
        "reference_id", "description",
    )
    readonly_fields = ("txn_id", "txn_id_display", "balance_after", "created_at")
    ordering = ("-created_at",)

    @admin.display(description="User")
    def get_user(self, obj):
        return obj.wallet.user.email


# ─────────────────────────────────────────────────────────────
# PAYMENT LOG
# ─────────────────────────────────────────────────────────────

@admin.register(PaymentLog)
class PaymentLogAdmin(admin.ModelAdmin):
    list_display  = ("log_id", "gateway", "event_type", "payment", "gateway_event_id", "created_at")
    list_filter   = ("gateway", "event_type")
    search_fields = ("log_id", "gateway_event_id", "payment__txn_id")
    readonly_fields = ("log_id", "created_at", "payload")
    ordering = ("-created_at",)