from __future__ import annotations   

from django.db import transaction
from decimal import Decimal
import logging

from payments.models import Wallet, WalletTransaction
from shopcore.models import CouponUsage

logger = logging.getLogger(__name__)

@transaction.atomic
def debit_from_wallet(
    user,
    amount: Decimal,
    description: str,
    reference_type: str = "ORDER",
    reference_id: str = "",
    order=None,
) -> tuple[bool, str, WalletTransaction | None]:
    try:
        wallet = Wallet.objects.select_for_update().get(user=user)
    except Wallet.DoesNotExist:
        return False, "No wallet found for this user.", None

    if wallet.balance < amount:
        return False, f"Insufficient balance (₹{wallet.balance:.2f} available).", None

    wallet.balance -= amount
    wallet.save(update_fields=["balance", "updated_at"])

    txn = WalletTransaction.objects.create(
        wallet=wallet,
        order=order,
        txn_type="DEBIT",
        amount=amount,
        balance_after=wallet.balance,
        reference_type=reference_type,
        reference_id=reference_id,
        description=description,
    )
    logger.info("Wallet debit: user=%s amount=%s txn=%s", user.email, amount, txn.txn_id)
    return True, "", txn


@transaction.atomic
def credit_refund_to_wallet(
    user,
    amount: Decimal,
    description: str,
    reference_type: str = "REFUND",
    reference_id: str = "",
    order=None,
) -> WalletTransaction:
    wallet, _ = Wallet.objects.select_for_update().get_or_create(user=user)
    wallet.balance += amount
    wallet.save(update_fields=["balance", "updated_at"])

    txn = WalletTransaction.objects.create(
        wallet=wallet,
        order=order,
        txn_type="REFUND",
        amount=amount,
        balance_after=wallet.balance,
        reference_type=reference_type,
        reference_id=reference_id,
        description=description,
    )
    logger.info("Wallet refund: user=%s amount=%s txn=%s", user.email, amount, txn.txn_id)
    return txn


@transaction.atomic
def credit_to_wallet(
    user,
    amount: Decimal,
    description: str,
    reference_type: str = "MANUAL",
    reference_id: str = "",
    order=None,
) -> WalletTransaction:
    wallet, _ = Wallet.objects.select_for_update().get_or_create(user=user)
    wallet.balance += amount
    wallet.save(update_fields=["balance", "updated_at"])

    txn = WalletTransaction.objects.create(
        wallet=wallet,
        order=order,
        txn_type="CREDIT",
        amount=amount,
        balance_after=wallet.balance,
        reference_type=reference_type,
        reference_id=reference_id,
        description=description,
    )
    logger.info("Wallet credit: user=%s amount=%s txn=%s", user.email, amount, txn.txn_id)
    return txn

#   ────────────────────────────────────────────────── INTERNAL HELPERS ──────────────────────────────────────────────────
def _restore_inventory_for_order(order) -> None:

    for oi in order.order_items.filter(item_status="PENDING"):
        try:
            inv = oi.variant.inventory
            inv.quantity_available += oi.quantity
            inv.quantity_sold = max(0, inv.quantity_sold - oi.quantity)
            inv.save(update_fields=["quantity_available", "quantity_sold"])
        except Exception:
            pass
        oi.item_status = "ORDER NOT PLACED"
        oi.save(update_fields=["item_status"])

def _finalize_order_after_payment(request, order):

    order.order_status = "PENDING"   # ← now officially placed
    order.save(update_fields=["order_status"])

    order.order_items.filter(item_status="PENDING").update(item_status="ACTIVE")

    # Apply coupon usage
    coupon_id = request.session.pop("pending_coupon_id", None)
    if coupon_id:
        from shopcore.models import Coupon
        try:
            coupon = Coupon.objects.get(id=coupon_id)
            usage, _ = CouponUsage.objects.get_or_create(
                coupon=coupon, user=order.user
            )
            usage.times_used += 1
            usage.save(update_fields=["times_used"])
            coupon.used_count += 1
            coupon.save(update_fields=["used_count"])
        except Exception:
            pass

    # Clear cart
    try:
        order.user.cart.items.all().delete()
    except Exception:
        pass

    request.session.pop("pending_paypal_order_id", None)
    request.session.pop("pending_kiddora_order_id", None)
    request.session.pop("applied_coupon_code", None)
    request.session.pop("applied_coupon_discount", None)