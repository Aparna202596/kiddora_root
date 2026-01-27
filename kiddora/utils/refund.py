from wallet.models import WalletTransaction
def partial_refund(return_obj, amount):
    wallet = return_obj.order.user.wallet

    if WalletTransaction.objects.filter(
        reference_type="RETURN",
        reference_id=str(return_obj.id)
    ).exists():
        return

    wallet.balance += amount
    wallet.save(update_fields=["balance"])

    WalletTransaction.objects.create(
        wallet=wallet,
        txn_type="REFUND",
        amount=amount,
        reference_type="RETURN",
        reference_id=str(return_obj.id)
    )

    return_obj.refund_amount = amount
    return_obj.status = "REFUNDED"
    return_obj.locked = True
    return_obj.save(update_fields=["refund_amount", "status", "locked"])
def full_refund(return_obj):
    wallet = return_obj.order.user.wallet
    refund_amount = return_obj.order.final_amount

    if WalletTransaction.objects.filter(
        reference_type="RETURN",
        reference_id=str(return_obj.id)
    ).exists():
        return

    wallet.balance += refund_amount
    wallet.save(update_fields=["balance"])

    WalletTransaction.objects.create(
        wallet=wallet,
        txn_type="REFUND",
        amount=refund_amount,
        reference_type="RETURN",
        reference_id=str(return_obj.id)
    )

    return_obj.refund_amount = refund_amount
    return_obj.status = "REFUNDED"
    return_obj.locked = True
    return_obj.save(update_fields=["refund_amount", "status", "locked"])