"""
payments/models.py
==================
Handles payment gateway integration for BOTH Stripe and Razorpay.
Orders live in shopcore. This app handles only the payment transaction layer.

DO NOT redefine Product / Category / Variant here — import from products/ only.

Transaction IDs are UUID-based for all payments (unique, non-sequential, safe to expose).
"""

from django.db import models
from django.utils import timezone
import uuid


# ─────────────────────────────────────────────────────────────────────────────
#  Payment
#  One Payment record per payment attempt.
#  Multiple attempts can exist per Order (retries after failure).
#  Supports Stripe, Razorpay, COD, and Wallet simultaneously.
# ─────────────────────────────────────────────────────────────────────────────
class Payment(models.Model):
    PAYMENT_METHOD_CHOICES = (
        ("RAZORPAY", "Razorpay"),
        ("STRIPE",   "Stripe"),
        ("COD",      "Cash on Delivery"),
        ("WALLET",   "Wallet"),
    )
    PAYMENT_STATUS_CHOICES = (
        ("PENDING",            "Pending"),
        ("INITIATED",          "Initiated"),       # Gateway order/intent created; user hasn't paid yet
        ("PAID",               "Paid"),
        ("FAILED",             "Failed"),
        ("REFUNDED",           "Refunded"),
        ("PARTIALLY_REFUNDED", "Partially Refunded"),
        ("CANCELLED",          "Cancelled"),
    )

    # ── Transaction ID ────────────────────────────────────────────────────────
    # UUID-based txn_id: unique, non-sequential, safe to show users and in invoices.
    # Generated automatically on save — never editable after creation.
    txn_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True,
        help_text="Universally unique transaction ID. Auto-generated. Use this in invoices and receipts.",
    )

    # ── Order link (string ref avoids circular import) ────────────────────────
    order = models.ForeignKey(
        "shopcore.Order",
        on_delete=models.CASCADE,
        related_name="payments",
    )

    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    payment_status = models.CharField(
        max_length=30,
        choices=PAYMENT_STATUS_CHOICES,
        default="PENDING",
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    # ── Razorpay-specific fields (null for Stripe / COD / Wallet) ─────────────
    # razorpay_order_id: created via Razorpay Orders API before checkout
    razorpay_order_id   = models.CharField(max_length=100, blank=True, null=True, unique=True,
                                            help_text="Razorpay order_id from Orders API (e.g. order_AbCdEf123).")
    # razorpay_payment_id: returned after user completes payment on Razorpay modal
    razorpay_payment_id = models.CharField(max_length=100, blank=True, null=True,
                                            help_text="Razorpay payment_id from payment.captured event.")
    # razorpay_signature: HMAC-SHA256 signature for server-side verification
    razorpay_signature  = models.CharField(max_length=256, blank=True, null=True,
                                            help_text="HMAC-SHA256 signature for Razorpay payment verification.")

    # ── Stripe-specific fields (null for Razorpay / COD / Wallet) ────────────
    # stripe_payment_intent_id: primary Stripe identifier — unique per payment attempt
    stripe_payment_intent_id = models.CharField(max_length=200, blank=True, null=True, unique=True,
                                                  help_text="Stripe PaymentIntent ID (e.g. pi_3AbCdEf...).")
    # stripe_client_secret: returned to frontend to confirm payment with Stripe.js
    stripe_client_secret     = models.CharField(max_length=500, blank=True, null=True,
                                                  help_text="Stripe client_secret for frontend confirmation.")
    # stripe_charge_id: populated after payment is captured / confirmed
    stripe_charge_id         = models.CharField(max_length=200, blank=True, null=True,
                                                  help_text="Stripe Charge ID populated after capture.")

    # ── Timestamps ────────────────────────────────────────────────────────────
    initiated_at = models.DateTimeField(null=True, blank=True,
                                         help_text="When the gateway order/intent was created.")
    completed_at = models.DateTimeField(null=True, blank=True,
                                         help_text="When payment was confirmed PAID or marked FAILED.")
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    # ── Failure / retry tracking ──────────────────────────────────────────────
    failure_reason = models.TextField(blank=True, null=True,
                                       help_text="Gateway error message on failure.")
    retry_count    = models.PositiveIntegerField(default=0,
                                                  help_text="Number of payment retries for this order.")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Payment"
        verbose_name_plural = "Payments"

    def __str__(self):
        return f"{self.txn_id} | {self.payment_method} | {self.payment_status} | {self.amount}"

    @property
    def txn_id_display(self):
        """Short display version of the UUID transaction ID (first 12 chars uppercase, no dashes)."""
        return str(self.txn_id).replace("-", "").upper()[:12]


# ─────────────────────────────────────────────────────────────────────────────
#  PaymentLog
#  Raw webhook / callback event log — one row per incoming event from either
#  Stripe or Razorpay. Used for debugging, audit trail, and idempotency checks.
# ─────────────────────────────────────────────────────────────────────────────
class PaymentLog(models.Model):
    GATEWAY_CHOICES = (
        ("RAZORPAY", "Razorpay"),
        ("STRIPE",   "Stripe"),
        ("INTERNAL", "Internal"),
    )
    EVENT_CHOICES = (
        # Razorpay events
        ("RZP_WEBHOOK",        "Razorpay Webhook"),
        ("RZP_CALLBACK",       "Razorpay Callback"),
        ("RZP_REFUND_WEBHOOK", "Razorpay Refund Webhook"),
        # Stripe events
        ("STRIPE_WEBHOOK",        "Stripe Webhook"),
        ("STRIPE_CALLBACK",       "Stripe Callback"),
        ("STRIPE_REFUND_WEBHOOK", "Stripe Refund Webhook"),
        # Generic
        ("MANUAL", "Manual Entry"),
    )

    # log_id: UUID for each log entry — safe for external references
    log_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        help_text="UUID identifying this log entry.",
    )

    payment    = models.ForeignKey(
        Payment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="logs",
        help_text="Associated Payment record (may be null if not yet matched).",
    )
    gateway    = models.CharField(max_length=20, choices=GATEWAY_CHOICES, default="INTERNAL")
    event_type = models.CharField(max_length=30, choices=EVENT_CHOICES)
    payload    = models.JSONField(default=dict, help_text="Raw event payload from gateway.")

    # Store gateway's own event/webhook ID for idempotency deduplication
    gateway_event_id = models.CharField(
        max_length=200, blank=True, null=True,
        help_text="Gateway's own event ID for deduplication "
                  "(e.g. Razorpay webhook ID or Stripe event ID evt_...).",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Payment Log"
        verbose_name_plural = "Payment Logs"

    def __str__(self):
        return f"PaymentLog {self.log_id} | {self.gateway} | {self.event_type} | {self.created_at:%Y-%m-%d %H:%M}"