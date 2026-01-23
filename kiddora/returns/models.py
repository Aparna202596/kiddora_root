from django.db import models
from orders.models import Order
from products.models import Product


class Return(models.Model):
    STATUS_CHOICES = (
        ("REQUESTED", "Requested"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
        ("REFUNDED", "Refunded"),
    )

    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    order_item = models.ForeignKey("orders.OrderItem", on_delete=models.CASCADE)
    locked = models.BooleanField(default=False)
