# payments/views/wallet_helpers.py
from __future__ import annotations

import logging
from decimal import Decimal

from django.db import transaction
from payments.models import Wallet, WalletTransaction
from shopcore.models import Order

logger = logging.getLogger(__name__)

@transaction.atomic
def debit_from_wallet(
    user,
    amount: Decimal,
    description: str,
    reference_type: str = "ORDER",
    reference_id: str = "",
    order: Order | None = None,
) -> tuple[bool, str, WalletTransaction | None]:
    try:
        wallet = Wallet.objects.select_for_update().get(user=user)
    except Wallet.DoesNotExist:
        return False, "No wallet found for this user.", None

    if wallet.balance < amount:
        return False, f"Insufficient balance (₹{wallet.balance:.2f} available)", None

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
    return True, "", txn


@transaction.atomic
def credit_refund_to_wallet(
    user,
    amount: Decimal,
    description: str,
    reference_type: str = "REFUND",
    reference_id: str = "",
    order: Order | None = None,
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
    return txn