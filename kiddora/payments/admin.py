from django.contrib import admin
from .models import *

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "order",
        "payment_method",
        "payment_status",
        "transaction_id",
        "paid_at"
    )
    list_filter = ("payment_status",)