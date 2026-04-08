from __future__ import annotations

import uuid

from accounts.models import CustomUser
from django.db import models
from django.utils import timezone
from shopcore.models import Order


#  ────────────────────────────────────────────────── PAYMENT ──────────────────────────────────────────────────
class Payment(models.Model):
    PAYMENT_METHOD_CHOICES = (
        ("PAYPAL", "PayPal"),
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

    txn_id = models.UUIDField(
        default=uuid.uuid4, unique=True, editable=False, db_index=True
    )

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="payments")

    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)

    payment_status = models.CharField(
        max_length=30, choices=PAYMENT_STATUS_CHOICES, default="PENDING"
    )

    amount = models.DecimalField(max_digits=10, decimal_places=2)

    failure_reason = models.TextField(blank=True, null=True)

    initiated_at = models.DateTimeField(null=True, blank=True)

    completed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    # ────────────────────── PayPal-specific fields ────────────────────────────────

    paypal_order_id = models.CharField(
        max_length=200, blank=True, null=True, unique=True
    )

    paypal_capture_id = models.CharField(max_length=200, blank=True, null=True)

    paypal_payer_id = models.CharField(max_length=200, blank=True, null=True)

    paypal_payer_email = models.EmailField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Payment"
        verbose_name_plural = "Payments"

    def __str__(self):
        return f"{self.txn_id_display} | {self.payment_method} | {self.payment_status} | ₹{self.amount}"

    @property
    def txn_id_display(self) -> str:
        return str(self.txn_id).replace("-", "").upper()[:12]


#   ────────────────────────────────────────────────── WALLET ──────────────────────────────────────────────────
class Wallet(models.Model):
    user = models.OneToOneField(
        CustomUser, on_delete=models.CASCADE, related_name="wallet"
    )

    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Wallet"
        verbose_name_plural = "Wallets"

    def __str__(self):
        return f"{self.user.email} | ₹{self.balance}"


#  ────────────────────────────────────────────────── WALLET TRANSACTION ──────────────────────────────────────────────────
class WalletTransaction(models.Model):
    TRANSACTION_TYPE_CHOICES = (
        ("CREDIT", "Credit"),
        ("DEBIT", "Debit"),
        ("REFUND", "Refund"),
    )
    REFERENCE_TYPE_CHOICES = (
        ("ORDER", "Order Payment"),
        ("RETURN", "Return Refund"),
        ("CANCEL", "Cancellation Refund"),
        ("REFERRAL", "Referral Reward"),
        ("MANUAL", "Admin Adjustment"),
    )

    wallet = models.ForeignKey(
        Wallet, on_delete=models.CASCADE, related_name="transactions"
    )

    order = models.ForeignKey(
        Order,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="wallet_transactions",
    )

    txn_id = models.UUIDField(
        default=uuid.uuid4, unique=True, editable=False, db_index=True
    )

    txn_type = models.CharField(
        max_length=20, choices=TRANSACTION_TYPE_CHOICES, default="CREDIT"
    )

    amount = models.DecimalField(max_digits=10, decimal_places=2)

    balance_after = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )

    reference_type = models.CharField(
        max_length=20, choices=REFERENCE_TYPE_CHOICES, blank=True
    )

    reference_id = models.CharField(max_length=50, blank=True)

    description = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Wallet Transaction"
        verbose_name_plural = "Wallet Transactions"

    def __str__(self):
        return f"{self.wallet.user.email} | {self.txn_type} | ₹{self.amount}"

    @property
    def txn_id_display(self) -> str:
        return str(self.txn_id).replace("-", "").upper()[:12]


#  ────────────────────────────────────────────────── PAYMENT LOG ──────────────────────────────────────────────────
class PaymentLog(models.Model):
    GATEWAY_CHOICES = (
        ("PAYPAL", "PayPal"),
        ("INTERNAL", "Internal"),
    )
    EVENT_CHOICES = (
        ("PAYPAL_WEBHOOK", "PayPal Webhook"),
        ("PAYPAL_CALLBACK", "PayPal Callback"),
        ("REFUND", "Refund Event"),
        ("MANUAL", "Manual Entry"),
    )

    log_id = models.UUIDField(
        default=uuid.uuid4, unique=True, editable=False, db_index=True
    )

    payment = models.ForeignKey(
        Payment, on_delete=models.SET_NULL, null=True, blank=True, related_name="logs"
    )

    gateway = models.CharField(
        max_length=20, choices=GATEWAY_CHOICES, default="INTERNAL"
    )

    event_type = models.CharField(max_length=30, choices=EVENT_CHOICES)

    payload = models.JSONField(default=dict, blank=True)

    gateway_event_id = models.CharField(max_length=200, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Payment Log"
        verbose_name_plural = "Payment Logs"

    def __str__(self):
        return f"{self.gateway} | {self.event_type} | {self.created_at:%Y-%m-%d %H:%M}"
