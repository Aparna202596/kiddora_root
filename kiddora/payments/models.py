from django.db import models
from shopcore.models import *
import uuid


class Payment(models.Model):
    PAYMENT_STATUS_CHOICES = (
        ("PENDING", "Pending"),
        ("PAID", "Paid"),
        ("FAILED", "Failed"),
        ("REFUNDED", "Refunded"),
    )

    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    payment_method = models.CharField(max_length=30)
    transaction_id = models.UUIDField(default=uuid.uuid4, unique=True)
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES)
    paid_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.TextField(null=True, blank=True)
    retry_allowed = models.BooleanField(default=True)
    refund_reference = models.CharField(max_length=50, null=True, blank=True)