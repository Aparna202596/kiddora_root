from django.contrib import admin
from .models import Payment, PaymentLog, Wallet, WalletTransaction

#  PAYMENT LOG (inline inside Payment)

class PaymentLogInline(admin.TabularInline):
    model = PaymentLog
    extra = 0
    fields = (
        "log_id", "gateway", "event_type",
        "gateway_event_id", "created_at",
    )
    readonly_fields = (
        "log_id", "gateway", "event_type",
        "gateway_event_id", "created_at",
    )
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

#  PAYMENT
@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display    = (
        "txn_id", "order", "payment_method", "payment_status",
        "amount", "retry_count", "initiated_at", "completed_at", "created_at",
    )
    list_filter = ("payment_method", "payment_status")
    search_fields = (
        "txn_id",
        "order__order_id",
        "razorpay_order_id",
        "razorpay_payment_id",
        "stripe_payment_intent_id",
    )
    readonly_fields = (
        "txn_id", "created_at", "updated_at",
        "initiated_at", "completed_at",
        "razorpay_order_id", "razorpay_payment_id", "razorpay_signature",
        "stripe_payment_intent_id", "stripe_client_secret", "stripe_charge_id",
    )
    inlines = [PaymentLogInline]
    ordering = ("-created_at",)

#  PAYMENT LOG (standalone)
@admin.register(PaymentLog)
class PaymentLogAdmin(admin.ModelAdmin):
    list_display = (
        "log_id", "payment", "gateway",
        "event_type", "gateway_event_id", "created_at",
    )
    list_filter = ("gateway", "event_type")
    search_fields = ("gateway_event_id", "payment__txn_id")
    readonly_fields = ("log_id", "payload", "created_at")
    ordering = ("-created_at",)

# ═══════════════════════════════════════════════════════════════
#  WALLET
# ═══════════════════════════════════════════════════════════════

class WalletTransactionInline(admin.TabularInline):
    model  = WalletTransaction
    extra  = 0
    fields = (
        "txn_id", "txn_type", "amount",
        "balance_after", "reference_type", "reference_id", "created_at",
    )
    readonly_fields = (
        "txn_id", "txn_type", "amount",
        "balance_after", "reference_type", "reference_id", "created_at",
    )
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display  = ("user", "balance", "created_at", "updated_at")
    search_fields = ("user__email",)
    readonly_fields = ("created_at", "updated_at")
    inlines = [WalletTransactionInline]
    ordering = ("-updated_at",)


@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display  = (
        "short_txn_id", "wallet", "txn_type", "amount",
        "balance_after", "reference_type", "reference_id",
        "description", "created_at",
    )
    list_filter   = ("txn_type", "reference_type")
    search_fields = ("wallet__user__email", "reference_id")
    readonly_fields = (
        "txn_id", "wallet", "txn_type", "amount",
        "balance_after", "reference_type", "reference_id",
        "description", "created_at",
    )
    ordering = ("-created_at",)

    @admin.display(description="Txn ID")
    def short_txn_id(self, obj):
        return obj.txn_id_display

