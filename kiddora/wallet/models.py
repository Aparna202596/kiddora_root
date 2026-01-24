from django.db import models
from accounts.models import CustomUser


class Wallet(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE)
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)


class WalletTransaction(models.Model):
    TRANSACTION_TYPE_CHOICES = (
        ("CREDIT", "Credit"),
        ("DEBIT", "Debit"),
        ("REFUND", "Refund"),
    )

    REFERENCE_TYPE_CHOICES = (
        ("ORDER", "Order"),
        ("RETURN", "Return"),
    )
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name="transactions")
    txn_type = models.CharField(max_length=20, choices=TRANSACTION_TYPE_CHOICES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    reference_type = models.CharField(max_length=20, choices=REFERENCE_TYPE_CHOICES, null=True, blank=True)
    reference_id = models.CharField(max_length=50, null=True, blank=True)
