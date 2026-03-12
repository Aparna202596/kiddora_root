# shopcore/services/order_life_cycle.py
# Centralised order lifecycle helpers used by views and signals.
# Fixed: uses item_status (not status) consistent with the OrderItem model.

from decimal import Decimal
from django.db import transaction
from django.utils import timezone

from products.services.inventory import release_stock


# ─────────────────────────────────────────────────────────────
# CANCEL a single OrderItem and restore its stock
# ─────────────────────────────────────────────────────────────

def cancel_order_item(order_item, reason="Cancelled"):
    """
    Cancels one OrderItem.
    - Sets item_status → CANCELLED
    - Releases reserved stock back to quantity_available
    - Does nothing if item is not ACTIVE
    """
    if order_item.item_status != "ACTIVE":
        return False

    order_item.item_status   = "CANCELLED"
    order_item.cancel_reason = reason
    order_item.cancelled_at  = timezone.now()
    order_item.save(update_fields=["item_status", "cancel_reason", "cancelled_at"])

    release_stock(order_item.variant, order_item.quantity)
    return True


# ─────────────────────────────────────────────────────────────
# CANCEL a whole Order
# ─────────────────────────────────────────────────────────────

@transaction.atomic
def cancel_entire_order(order, reason="Cancelled by user"):
    """
    Cancels an order if it is PENDING or CONFIRMED.
    Calls cancel_order_item for each ACTIVE item.
    """
    if order.order_status not in ("PENDING", "CONFIRMED"):
        return False

    for item in order.order_items.filter(item_status="ACTIVE"):
        cancel_order_item(item, reason=reason)

    order.order_status  = "CANCELLED"
    order.cancel_reason = reason
    order.cancelled_at  = timezone.now()
    order.save(update_fields=["order_status", "cancel_reason", "cancelled_at"])
    return True


# ─────────────────────────────────────────────────────────────
# MARK ORDER DELIVERED
# ─────────────────────────────────────────────────────────────

@transaction.atomic
def mark_order_delivered(order):
    """
    Sets order_status → DELIVERED and marks every ACTIVE item as DELIVERED.
    The post_save signal on OrderItem will call deduct_stock_on_delivery.
    """
    for item in order.order_items.filter(item_status="ACTIVE"):
        item.item_status = "DELIVERED"
        item.save(update_fields=["item_status"])

    order.order_status   = "DELIVERED"
    order.delivered_at   = timezone.now()
    order.payment_status = "PAID"
    order.save(update_fields=["order_status", "delivered_at", "payment_status"])


# ─────────────────────────────────────────────────────────────
# COMPUTE ORDER TOTALS
# ─────────────────────────────────────────────────────────────

def compute_order_totals(cart_items, coupon=None):
    """
    Given a list/queryset of CartItems, return a dict with:
      subtotal, discount_amount, coupon_discount, shipping_charge, final_amount
    """
    subtotal        = sum(
        item.variant.product.final_price * item.quantity
        for item in cart_items
    )
    discount_amount = Decimal("0")
    coupon_discount = Decimal("0")
    shipping_charge = Decimal("0")   # extend with real shipping logic

    if coupon and coupon.is_valid():
        if coupon.discount_type == "PERCENT":
            coupon_discount = subtotal * coupon.discount_value / 100
            if coupon.max_discount:
                coupon_discount = min(coupon_discount, coupon.max_discount)
        else:
            coupon_discount = coupon.discount_value
        coupon_discount = min(coupon_discount, subtotal)

    final_amount = subtotal - discount_amount - coupon_discount + shipping_charge

    return {
        "subtotal":        subtotal,
        "discount_amount": discount_amount,
        "coupon_discount": coupon_discount,
        "shipping_charge": shipping_charge,
        "final_amount":    final_amount,
    }
