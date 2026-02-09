from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.views.decorators.cache import never_cache
from products.models import*
from accounts.decorators import admin_login_required
from products.services.inventory import reserve_stock, release_stock, deduct_stock_on_delivery

# ---------------- INVENTORY ----------------
@admin_login_required
def admin_inventory_list(request):
    inventory = Inventory.objects.select_related("variant", "variant__product")
    return render(request, "products/admin/admin_inventory.html", {"inventory": inventory})


@admin_login_required
def admin_update_stock(request, inventory_id):
    inventory = get_object_or_404(Inventory, id=inventory_id)
    if request.method == "POST":
        try:
            change = int(request.POST.get("quantity"))
            inventory.quantity_available += change
            inventory.save()
            messages.success(request, "Stock updated successfully")
        except Exception as e:
            messages.error(request, f"Error updating stock: {str(e)}")
        return redirect("products:admin_inventory_list")