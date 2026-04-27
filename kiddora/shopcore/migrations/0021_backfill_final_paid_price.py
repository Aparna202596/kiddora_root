from django.db import migrations
from decimal import Decimal

def backfill_paid_prices(apps, schema_editor):
    OrderItem = apps.get_model("shopcore", "OrderItem")
    Order = apps.get_model("shopcore", "Order")

    for order in Order.objects.prefetch_related("order_items").all():
        items = list(order.order_items.all())
        if not items:
            continue

        items_post_offer_total = sum(
            (oi.total_price)   # total_price already = unit_price*qty - offer_discount
            for oi in items
        ) or Decimal("1")

        coupon_discount = order.coupon_discount or Decimal("0")

        for oi in items:
            post_offer_line = oi.total_price

            item_coupon_share = (
                (post_offer_line / items_post_offer_total) * coupon_discount
            ).quantize(Decimal("0.01")) if coupon_discount else Decimal("0")

            item_final_paid = (post_offer_line - item_coupon_share).quantize(Decimal("0.01"))

            oi.coupon_discount_share = item_coupon_share
            oi.final_paid_price = item_final_paid
            oi.save(update_fields=["coupon_discount_share", "final_paid_price"])

class Migration(migrations.Migration):
    dependencies = [
        ("shopcore", '0020_add_final_paid_price_to_orderitem'),  
    ]
    operations = [
        migrations.RunPython(backfill_paid_prices, migrations.RunPython.noop),
    ]