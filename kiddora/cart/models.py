from django.db import models
from accounts.models import CustomUser
from products.models import ProductVariant

class Cart(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE)
    updated_at = models.DateTimeField(auto_now=True)
    def __str__(self):
        return f"Cart - {self.user.username}"
class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    class Meta:
        unique_together = ("cart", "variant")
