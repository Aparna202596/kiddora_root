from django.db import transaction
from django.db.models.signals import post_save,post_delete
from django.db.models import Avg
from django.dispatch import receiver
# from django.utils.timezone import now
from django.utils import timezone
from decimal import Decimal
import math
from products.models import Inventory
from products.services.inventory import release_stock, deduct_stock_on_delivery
from shopcore.models import OrderItem, Return, Review, ReferralCode
from payments.models import Wallet, WalletTransaction
from accounts.models import CustomUser

# ─────────────────────────────────────────────────────────────
# ORDER ITEM: reserve inventory on creation
# ─────────────────────────────────────────────────────────────

@receiver(post_save, sender=OrderItem)
def reserve_inventory(sender, instance, created, **kwargs):
    """When an OrderItem is first created, move qty from available → reserved."""
    if created:
        try:
            inventory = Inventory.objects.get(variant=instance.variant)
            inventory.quantity_available -= instance.quantity
            inventory.quantity_reserved  += instance.quantity
            inventory.save(update_fields=["quantity_available", "quantity_reserved"])
        except Inventory.DoesNotExist:
            pass


# ─────────────────────────────────────────────────────────────
# ORDER ITEM: handle status transitions
# ─────────────────────────────────────────────────────────────

@receiver(post_save, sender=OrderItem)
def handle_order_item_status(sender, instance, created, **kwargs):
    """
    CANCELLED → release reserved stock back to available.
    DELIVERED  → move reserved stock to sold (via deduct_stock_on_delivery).
    Skip on creation — reserve_inventory handles that.
    """
    if created:
        return
    if instance.item_status == "CANCELLED":
        release_stock(instance.variant, instance.quantity)
    elif instance.item_status == "DELIVERED":
        deduct_stock_on_delivery(instance.variant, instance.quantity)


# ─────────────────────────────────────────────────────────────
# RETURN: combined refund + restock on REFUNDED status
# ─────────────────────────────────────────────────────────────

@receiver(post_save, sender=Return)
def handle_return_status(sender, instance, **kwargs):
    """
    APPROVED  → restock inventory (quantity_available += qty).
    REFUNDED  → credit wallet + ensure inventory is restocked.

    Uses `instance.locked` to prevent double-execution.
    Add `locked = models.BooleanField(default=False)` to the Return model.
    """
    if kwargs.get("update_fields") and "locked" in kwargs["update_fields"]:
        # This save was triggered by us setting locked=True — skip
        return

    if instance.status == "APPROVED" and not instance.locked:
        _restock_inventory(instance)

    elif instance.status == "REFUNDED" and not instance.locked:
        with transaction.atomic():
            _restock_inventory(instance)
            _credit_wallet(instance)
            Return.objects.filter(pk=instance.pk).update(locked=True)


def _restock_inventory(ret):
    """Add returned quantity back to quantity_available."""
    try:
        inventory = ret.order_item.variant.inventory
        inventory.quantity_available += ret.order_item.quantity
        inventory.save(update_fields=["quantity_available"])
    except Exception:
        pass

HALF_LIFE_DAYS = 90


def compute_weighted_average(product):
    """
    Weighted average rating using recency weights.

    weight(review) = e ^ (- days_since_review / HALF_LIFE_DAYS)

    weighted_avg = Sum(rating_i * weight_i) / Sum(weight_i)

    Returns a Decimal rounded to 2 places, or 0.00 if no approved reviews.
    """
    reviews = product.reviews.filter(is_approved=True).only("rating", "created_at")

    if not reviews.exists():
        return Decimal("0.00")

    now             = timezone.now()
    weighted_sum    = 0.0
    total_weight    = 0.0

    for review in reviews:
        days_old = (now - review.created_at).total_seconds() / 86400  # convert to days
        weight   = math.exp(-days_old / HALF_LIFE_DAYS)               # exponential decay

        weighted_sum += review.rating * weight
        total_weight += weight

    if total_weight == 0:
        return Decimal("0.00")

    raw_avg = weighted_sum / total_weight                   # float between 1.0 – 5.0
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
            wallet      = wallet,
            txn_type    = "REFUND",
            amount      = amount,
            description = f"Refund for order {ret.order_item.order.order_id}",
        )
    except Exception:
        pass

# ─────────────────────────────────────────────────────────────
# AUTO-GENERATE REFERRAL CODE ON USER CREATION (THE REQUIRED ADDON)
# ─────────────────────────────────────────────────────────────
@receiver(post_save, sender=CustomUser)
def create_referral_record_for_new_user(sender, instance, created, **kwargs):
    """Automatically create ReferralCode + token + code when any new user is created."""
    if created:
        ReferralCode.objects.get_or_create(
            user=instance,
            defaults={"code": ReferralCode.fresh_code()},
        )