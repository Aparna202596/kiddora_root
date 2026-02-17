from django.db.models.signals import post_save
from django.dispatch import receiver
from appkiddora.models import OrderItem
from products.models import Inventory
from django.db.models.signals import post_save
from django.dispatch import receiver
from products.services.inventory import release_stock, deduct_stock_on_delivery

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.core.exceptions import ValidationError
from django.utils.timezone import now
from datetime import timedelta
from appkiddora.models import *
from products.models import Inventory
from django.db import transaction

#ORDER
@receiver(post_save, sender=OrderItem)
def reserve_inventory(sender, instance, created, **kwargs):
    if created:
        inventory = Inventory.objects.get(variant=instance.variant)
        inventory.quantity_available -= instance.quantity
        inventory.quantity_reserved += instance.quantity
        inventory.save()

@receiver(post_save, sender=OrderItem)
def handle_order_item_status(sender, instance, **kwargs):
    if instance.status == "CANCELLED":
        release_stock(instance.variant, instance.quantity)

    if instance.status == "DELIVERED":
        deduct_stock_on_delivery(instance.variant, instance.quantity)

#RETURN


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
