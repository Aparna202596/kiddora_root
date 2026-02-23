from django.utils import timezone
from products.services.inventory import release_stock

def cancel_order_item(order_item):
    if order_item.status != "ACTIVE":
        return
    order_item.status = "CANCELLED"
    order_item.save()
    release_stock(order_item.variant, order_item.quantity)

def mark_order_delivered(order):
    for item in order.items.all():
        item.status = "ACTIVE"
        item.save()
    order.order_status = "DELIVERED"
    order.delivered_at = timezone.now()
    order.save()
