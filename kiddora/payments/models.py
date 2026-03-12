from django.db import models
from django.utils import timezone
from shopcore.models import Order
from accounts.models import CustomUser
import uuid

class Payment(models.Model):
    PAYMENT_METHOD_CHOICES = (
        ("RAZORPAY", "Razorpay"),
        ("STRIPE", "Stripe"),
        ("COD", "Cash on Delivery"),
        ("WALLET", "Wallet"),
    )
    PAYMENT_STATUS_CHOICES = (
        ("PENDING", "Pending"),
        ("INITIATED", "Initiated"),
        ("PAID", "Paid"),
        ("FAILED", "Failed"),
        ("REFUNDED", "Refunded"),
        ("PARTIALLY_REFUNDED", "Partially Refunded"),
        ("CANCELLED", "Cancelled"),
    )

    txn_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="payments")
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    payment_status = models.CharField(max_length=30, choices=PAYMENT_STATUS_CHOICES, default="PENDING")
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    # Razorpay-specific (null for Stripe / COD / Wallet)
    razorpay_order_id = models.CharField(max_length=100, blank=True, null=True, unique=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_signature = models.CharField(max_length=256,  blank=True, null=True)

    # Stripe-specific (null for Razorpay / COD / Wallet)
    stripe_payment_intent_id = models.CharField(max_length=200, blank=True, null=True, unique=True)
    stripe_client_secret = models.CharField(max_length=500, blank=True, null=True)
    stripe_charge_id = models.CharField(max_length=200, blank=True, null=True)

    initiated_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    failure_reason = models.TextField(blank=True, null=True)
    retry_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Payment"
        verbose_name_plural = "Payments"

    def __str__(self):
        return f"{self.txn_id} | {self.payment_method} | {self.payment_status} | {self.amount}"

    @property
    def txn_id_display(self):
        return str(self.txn_id).replace("-", "").upper()[:12]


class PaymentLog(models.Model):
    GATEWAY_CHOICES = (
        ("PAYPAL", "PAYPAL"),
        ("STRIPE", "Stripe"),
        ("INTERNAL", "Internal"),
    )
    EVENT_CHOICES = (
        ("RZP_WEBHOOK", "Razorpay Webhook"),
        ("RZP_CALLBACK", "Razorpay Callback"),
        ("RZP_REFUND_WEBHOOK", "Razorpay Refund Webhook"),
        ("STRIPE_WEBHOOK", "Stripe Webhook"),
        ("STRIPE_CALLBACK", "Stripe Callback"),
        ("STRIPE_REFUND_WEBHOOK", "Stripe Refund Webhook"),
        ("MANUAL", "Manual Entry"),
    )

    log_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    payment = models.ForeignKey(Payment, on_delete=models.SET_NULL, null=True, blank=True, related_name="logs")
    gateway = models.CharField(max_length=20, choices=GATEWAY_CHOICES, default="INTERNAL")
    event_type = models.CharField(max_length=30, choices=EVENT_CHOICES)
    payload = models.JSONField(default=dict, blank=True)
    gateway_event_id = models.CharField(max_length=200, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Payment Log"
        verbose_name_plural = "Payment Logs"

    def __str__(self):
        return (
            f"PaymentLog {self.log_id} | {self.gateway} | "
            f"{self.event_type} | {self.created_at:%Y-%m-%d %H:%M}"
        )

#  WALLET
class Wallet(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name="wallet")
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Wallet – {self.user.email} (₹{self.balance})"

class WalletTransaction(models.Model):
    TRANSACTION_TYPE_CHOICES = (
        ("CREDIT",  "Credit"),
        ("DEBIT",   "Debit"),
        ("REFUND",  "Refund"),
    )
    REFERENCE_TYPE_CHOICES = (
        ("ORDER", "Order"),
        ("RETURN", "Return"),
        ("REFERRAL", "Referral Reward"),
        ("COUPON", "Coupon Refund"),
        ("MANUAL", "Manual Adjustment"),
    )

    wallet         = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name="transactions")
    txn_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    txn_type = models.CharField(max_length=20, choices=TRANSACTION_TYPE_CHOICES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    balance_after = models.DecimalField(max_digits=10, decimal_places=2)
    reference_type = models.CharField(max_length=20, choices=REFERENCE_TYPE_CHOICES, null=True, blank=True)
    reference_id = models.CharField(max_length=50, null=True, blank=True)
    description = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.txn_id} | {self.txn_type} {self.amount}"

    @property
    def txn_id_display(self):
        """Short display version of the UUID txn_id (first 12 chars, no dashes)."""
        return str(self.txn_id).replace("-", "").upper()[:12]