from django.db import models
from accounts.models import CustomUser
from products.models import Product


class Review(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    rating = models.PositiveIntegerField()
    comment = models.TextField()

    class Meta:
        unique_together = ("user", "product")
