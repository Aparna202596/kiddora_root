from django.db import transaction
from products.models import Inventory

def reserve_stock(variant, quantity):
    with transaction.atomic():
        inventory = Inventory.objects.select_for_update().get(variant=variant)
        if inventory.quantity_available < quantity:
            raise ValueError("Insufficient stock")
        inventory.quantity_available -= quantity
        inventory.quantity_reserved += quantity
        inventory.save()

def release_stock(variant, quantity):
    with transaction.atomic():
        inventory = Inventory.objects.select_for_update().get(variant=variant)
        inventory.quantity_available += quantity
        inventory.quantity_reserved -= quantity
        inventory.save()

def deduct_stock_on_delivery(variant, quantity):
    with transaction.atomic():
        inventory = Inventory.objects.select_for_update().get(variant=variant)
        inventory.quantity_reserved -= quantity
        inventory.save()
