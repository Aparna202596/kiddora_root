from django.db.models.signals import post_save
from django.dispatch import receiver
from orders.models import OrderItem
from products.models import Inventory


@receiver(post_save, sender=OrderItem)
def reserve_inventory(sender, instance, created, **kwargs):
    if created:
        inventory = Inventory.objects.get(variant=instance.variant)
        inventory.quantity_available -= instance.quantity
        inventory.quantity_reserved += instance.quantity
        inventory.save()
