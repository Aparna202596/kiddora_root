from __future__ import annotations

import logging
from decimal import Decimal

from django.db import transaction

from payments.models import Wallet, WalletTransaction
from shopcore.models import Order

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# DEBIT  (used when customer pays with wallet)
# ─────────────────────────────────────────────────────────────

@transaction.atomic
def debit_from_wallet(
    user,
    amount: Decimal,
    description: str,
    reference_type: str = "ORDER",
    reference_id: str = "",
    order: Order | None = None,
) -> tuple[bool, str, WalletTransaction | None]:
    """
    Debit *amount* from the user's wallet.
    Returns (success, error_message, transaction_or_None).
    """
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


# ─────────────────────────────────────────────────────────────
# CREDIT REFUND  (used for return / cancellation refunds)
# ─────────────────────────────────────────────────────────────

@transaction.atomic
def credit_refund_to_wallet(
    user,
    amount: Decimal,
    description: str,
    reference_type: str = "REFUND",
    reference_id: str = "",
    order: Order | None = None,
) -> WalletTransaction:
    """
    Credit *amount* to the user's wallet (refund path).
    Creates the wallet if it doesn't exist yet.
    Always succeeds (raises on DB error).
    """
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


# ─────────────────────────────────────────────────────────────
# CREDIT  (used for referral rewards / manual admin top-ups)
# ─────────────────────────────────────────────────────────────

@transaction.atomic
def credit_to_wallet(
    user,
    amount: Decimal,
    description: str,
    reference_type: str = "MANUAL",
    reference_id: str = "",
    order: Order | None = None,
) -> WalletTransaction:
    """
    Generic credit – referral rewards, admin adjustments, etc.
    """
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