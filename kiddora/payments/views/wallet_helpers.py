from __future__ import annotations

import logging
from decimal import Decimal

from django.db import transaction
from payments.models import Wallet, WalletTransaction
from shopcore.models import CouponUsage, Coupon

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
    logger.info(
        "Wallet debit: user=%s amount=%s txn=%s", user.email, amount, txn.txn_id
    )
    return True, "", txn

@transaction.atomic
def credit_refund_to_wallet(
    user,
    amount: Decimal,
    description: str,
    reference_type: str = "REFUND",
    reference_id: str = "",
    order=None,
) -> WalletTransaction | None:
    wallet, _ = Wallet.objects.select_for_update().get_or_create(user=user)

    already_refunded = WalletTransaction.objects.filter(
        wallet=wallet,
        txn_type="REFUND",
        reference_type=reference_type,
        reference_id=reference_id,
    ).exists()

    if already_refunded:
        logger.warning(
            "Duplicate refund blocked: user=%s reference_type=%s reference_id=%s",
            user.email,
            reference_type,
            reference_id,
        )
        return None

    wallet.balance += amount
    wallet.save(update_fields=["balance", "updated_at"])

    try:
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
    except Exception:
        logger.warning(
            "Concurrent duplicate refund blocked via DB constraint: user=%s reference_id=%s",
            user.email,
            reference_id,
        )
        raise

    logger.info(
        "Wallet refund: user=%s amount=%s reference_id=%s txn=%s",
        user.email,
        amount,
        reference_id,
        txn.txn_id,
    )
    return txn

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
    order.order_status = "PENDING"
    order.save(update_fields=["order_status"])
    order.order_items.filter(item_status="PENDING").update(item_status="ACTIVE")

    coupon_id = request.session.pop("pending_coupon_id", None)
    if coupon_id:

        try:
            coupon = Coupon.objects.get(id=coupon_id)
            usage, _ = CouponUsage.objects.get_or_create(coupon=coupon, user=order.user)
            usage.times_used += 1
            usage.save(update_fields=["times_used"])
            coupon.used_count += 1
            coupon.save(update_fields=["used_count"])
        except Exception:
            pass

    try:
        order.user.cart.items.all().delete()
    except Exception:
        pass

    request.session.pop("pending_paypal_order_id", None)
    request.session.pop("pending_kiddora_order_id", None)
    request.session.pop("applied_coupon_code", None)
    request.session.pop("applied_coupon_discount", None)
