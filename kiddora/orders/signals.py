from django.db.models.signals import post_save
from django.dispatch import receiver
from orders.models import OrderItem
from products.models import Inventory
from django.db.models.signals import post_save
from django.dispatch import receiver
from orders.models import OrderItem
from products.services.inventory import release_stock, deduct_stock_on_delivery

@receiver(post_save, sender=OrderItem)
def reserve_inventory(sender, instance, created, **kwargs):
    if created:
        inventory = Inventory.objects.get(variant=instance.variant)
        inventory.quantity_available -= instance.quantity
        inventory.quantity_reserved += instance.quantity
        inventory.save()

@receiver(post_save, sender=OrderItem)
def handle_order_item_status(sender, instance, **kwargs):
    if instance.status == "CANCELLED":
        release_stock(instance.variant, instance.quantity)

    if instance.status == "DELIVERED":
        deduct_stock_on_delivery(instance.variant, instance.quantity)