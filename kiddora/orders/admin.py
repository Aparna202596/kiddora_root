from django.contrib import admin
from .models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "id", "user", "order_status",
        "payment_status", "final_amount", "order_date"
    )
    list_filter = ("order_status", "payment_status")
    inlines = [OrderItemInline]
    ordering = ("-order_date",)
