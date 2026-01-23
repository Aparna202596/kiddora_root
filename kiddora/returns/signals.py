from django.db.models.signals import post_save
from django.dispatch import receiver
from returns.models import Return
from wallet.models import WalletTransaction


@receiver(post_save, sender=Return)
def refund_to_wallet(sender, instance, **kwargs):
    if instance.status == "REFUNDED":
        wallet = instance.order.user.wallet
        refund_amount = instance.order.final_amount
        wallet.balance += refund_amount
        wallet.save()

        WalletTransaction.objects.create(
            wallet=wallet,
            txn_type="REFUND",
            amount=refund_amount
        )
