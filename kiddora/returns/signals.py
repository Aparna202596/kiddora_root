from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.core.exceptions import ValidationError
from django.utils.timezone import now
from datetime import timedelta
from returns.models import Return
from products.models import Inventory
from wallet.models import Wallet,WalletTransaction
from django.db import transaction

@receiver(post_save, sender=Return)
def refund_to_wallet(sender, instance, **kwargs):
    if instance.status == "REFUNDED" and not instance.locked:
        wallet = instance.order.user.wallet
        refund_amount = instance.order.final_amount
        #amount = instance.refund_amount
        wallet.balance += refund_amount
        #wallet.balance += amount
        wallet.save()

        WalletTransaction.objects.create(
            wallet=wallet,
            txn_type="REFUND",
            amount=refund_amount
        )
        instance.locked = True
        instance.save(update_fields=["locked"])

@receiver(post_save, sender=Return)
def restock_inventory_on_approved_return(sender, instance, **kwargs):
    if instance.status == "APPROVED" and not instance.locked:
        inventory = instance.order_item.variant.inventory
        inventory.quantity_available += instance.order_item.quantity
        inventory.save(update_fields=["quantity_available"])



@receiver(post_save, sender=Return)
def refund_to_wallet_on_return(sender, instance, **kwargs):
    if instance.status == "REFUNDED" and not instance.locked:
        with transaction.atomic():
            # Wallet refund
            wallet = instance.order.user.wallet
            amount = instance.refund_amount or instance.order_item.total_price
            wallet.balance += amount
            wallet.save()

            WalletTransaction.objects.create(
                wallet=wallet,
                txn_type="REFUND",
                amount=amount
            )

            # Restock inventory if not already done
            inventory = instance.order_item.variant.inventory
            inventory.quantity_available += instance.order_item.quantity
            inventory.save(update_fields=["quantity_available"])

            instance.locked = True
            instance.save(update_fields=["locked"])
