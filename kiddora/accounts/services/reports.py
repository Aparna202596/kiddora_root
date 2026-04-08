from django.db.models import Sum
from shopcore.models import *


def sales_report(start, end):
    return Order.objects.filter(
        order_date__range=[start, end], payment_status="PAID"
    ).aggregate(total_orders=Sum("id"), total_revenue=Sum("final_amount"))
