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

    order = models.ForeignKey(Order, on_delete=models.CASCADE,related_name="item_returns")
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    order_item = models.ForeignKey("orders.OrderItem", on_delete=models.CASCADE)
    refund_amount = models.DecimalField(max_digits=10,decimal_places=2,null=True,blank=True)
    locked = models.BooleanField(default=False)
