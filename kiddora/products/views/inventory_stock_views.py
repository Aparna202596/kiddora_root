from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction

from accounts.decorators import admin_login_required
from products.models import Inventory, ProductVariant


# -----------------------------
# INVENTORY DASHBOARD
# -----------------------------
@admin_login_required
def admin_inventory_list(request):

    inventories = Inventory.objects.select_related(
        "variant", "variant__product"
    ).order_by("-updated_at")

    return render(
        request,
        "products/admin/admin_inventory_list.html",
        {"inventories": inventories},
    )


# -----------------------------
# UPDATE STOCK
# -----------------------------
@admin_login_required
@transaction.atomic
def update_stock(request, variant_id):

    inventory = get_object_or_404(Inventory, variant_id=variant_id)

    if request.method == "POST":
        change = int(request.POST.get("change", 0))
        action = request.POST.get("action")

        if action == "add":
            inventory.quantity_available += change

        elif action == "remove":
            if change > inventory.quantity_available:
                messages.error(request, "Not enough stock")
                return redirect("products:admin_inventory_list")
            inventory.quantity_available -= change

        inventory.save()
        messages.success(request, "Stock updated")

    return redirect("products:admin_inventory_list")


# -----------------------------
# AUTO SYNC (orders/cancel/return hook)
# -----------------------------
def sync_inventory(variant: ProductVariant, delta_available=0, delta_reserved=0, delta_sold=0):
    """
    Utility function to be used by order services
    """

    inventory, _ = Inventory.objects.get_or_create(
        variant=variant, defaults={"quantity_available": 0}
    )

    inventory.quantity_available += delta_available
    inventory.quantity_reserved += delta_reserved
    inventory.quantity_sold += delta_sold
    inventory.save()