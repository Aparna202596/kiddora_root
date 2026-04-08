from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.timezone import now
from payments.models import Payment, WalletTransaction


@receiver(post_save, sender=Payment)
def auto_wallet_refund_on_failure(sender, instance, created, **kwargs):

    if instance.payment_status != "FAILED":
        return
    if instance.payment_method != "WALLET":
        return

    # Prevent double refund
    if WalletTransaction.objects.filter(
        reference_type="ORDER", reference_id=str(instance.order.id), txn_type="REFUND"
    ).exists():
        return

    try:
        wallet = instance.order.user.wallet
    except Exception:
        return

    wallet.balance += instance.amount
    wallet.save(update_fields=["balance"])
    WalletTransaction.objects.create(
        wallet=wallet,
        txn_type="REFUND",
        amount=instance.amount,
        reference_type="ORDER",
        reference_id=str(instance.order.id),
    )
