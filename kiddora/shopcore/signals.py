import math
from decimal import Decimal

from accounts.models import CustomUser
from django.db import transaction
from django.db.models import Avg
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
# from django.utils.timezone import now
from django.utils import timezone
from payments.models import Wallet, WalletTransaction
from products.models import Inventory
from products.services.inventory import deduct_stock_on_delivery, release_stock
from shopcore.models import OrderItem, ReferralCode, Return, Review

# ────────────────────────────────────────── ORDER ITEM: reserve inventory on creation ──────────────────────────────────────────

@receiver(post_save, sender=OrderItem)
def reserve_inventory(sender, instance, created, **kwargs):
    """When an OrderItem is first created, move qty from available → reserved."""
    if created:
        try:
            inventory = Inventory.objects.get(variant=instance.variant)
            inventory.quantity_available -= instance.quantity
            inventory.quantity_reserved += instance.quantity
            inventory.save(update_fields=["quantity_available", "quantity_reserved"])
        except Inventory.DoesNotExist:
            pass

# ────────────────────────────────────────── ORDER ITEM: handle status transitions ──────────────────────────────────────────


@receiver(post_save, sender=OrderItem)
def handle_order_item_status(sender, instance, created, **kwargs):

    if created:
        return
    if instance.item_status == "CANCELLED":
        release_stock(instance.variant, instance.quantity)
    elif instance.item_status == "DELIVERED":
        deduct_stock_on_delivery(instance.variant, instance.quantity)

# ────────────────────────────────────────── RETURN: combined refund + restock on REFUNDED status ──────────────────────────────────────────
@receiver(post_save, sender=Return)
def handle_return_status(sender, instance, **kwargs):

    if kwargs.get("update_fields") and "locked" in kwargs["update_fields"]:

        return

    if instance.status == "APPROVED" and not instance.locked:
        _restock_inventory(instance)

    elif instance.status == "REFUNDED" and not instance.locked:
        with transaction.atomic():
            _restock_inventory(instance)
            _credit_wallet(instance)
            Return.objects.filter(pk=instance.pk).update(locked=True)


def _restock_inventory(ret):

    try:
        inventory = ret.order_item.variant.inventory
        inventory.quantity_available += ret.order_item.quantity
        inventory.save(update_fields=["quantity_available"])
    except Exception:
        pass


HALF_LIFE_DAYS = 90


def compute_weighted_average(product):

    reviews = product.reviews.filter(is_approved=True).only("rating", "created_at")

    if not reviews.exists():
        return Decimal("0.00")

    now = timezone.now()
    weighted_sum = 0.0
    total_weight = 0.0

    for review in reviews:
        days_old = (now - review.created_at).total_seconds() / 86400  
        weight = math.exp(-days_old / HALF_LIFE_DAYS)  

        weighted_sum += review.rating * weight
        total_weight += weight

    if total_weight == 0:
        return Decimal("0.00")

    raw_avg = weighted_sum / total_weight  
    return Decimal(str(round(raw_avg, 2)))


def update_product_average(product):
    """Recalculate and persist the weighted average on the Product."""
    product.average_review = compute_weighted_average(product)
    product.save(update_fields=["average_review"])


@receiver(post_save, sender=Review)
def update_average_on_save(sender, instance, **kwargs):
    """Fires when a review is created or updated (e.g. approved)."""
    update_product_average(instance.product)


@receiver(post_delete, sender=Review)
def update_average_on_delete(sender, instance, **kwargs):
    """Fires when a review is deleted."""
    update_product_average(instance.product)


def _credit_wallet(ret):
    """Credit the refund amount to the user's wallet."""
    try:
        amount = ret.refund_amount or ret.order_item.total_price
        wallet, _ = Wallet.objects.get_or_create(user=ret.order_item.order.user)
        wallet.balance += amount
        wallet.save(update_fields=["balance"])
        WalletTransaction.objects.create(
            wallet=wallet,
            txn_type="REFUND",
            amount=amount,
            description=f"Refund for order {ret.order_item.order.order_id}",
        )
    except Exception:
        pass

# ────────────────────────────────────────── AUTO-GENERATE REFERRAL CODE ON USER CREATION (THE REQUIRED ADDON) ──────────────────────────────────────────
@receiver(post_save, sender=CustomUser)
def create_referral_record_for_new_user(sender, instance, created, **kwargs):

    if created:
        ReferralCode.objects.get_or_create(
            user=instance,
            defaults={"code": ReferralCode.fresh_code()},
        )