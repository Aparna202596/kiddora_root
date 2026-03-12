from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.views.decorators.cache import never_cache
from accounts.decorators import admin_login_required
from products.models import Inventory, ProductVariant
from products.utils.search_utils import apply_search
from products.utils.pagination import paginate_queryset


@never_cache
@admin_login_required
def admin_inventory_list(request):
    search   = request.GET.get("search", "").strip()
    sort     = request.GET.get("sort", "-updated")  # default: newest first
    stock_f  = request.GET.get("stock_filter", "")  # "low" | "out" | ""

    # ADD-ON: map URL sort param → ORM order_by expression
    SORT_MAP = {
        "product":  "variant__product__product_name",
        "-product": "-variant__product__product_name",
        "stock":    "quantity_available",
        "-stock":   "-quantity_available",
        "sold":     "quantity_sold",
        "-sold":    "-quantity_sold",
        "updated":  "updated_at",
        "-updated": "-updated_at",
    }
    order_field = SORT_MAP.get(sort, "-updated_at")

    inventories = (
        Inventory.objects.select_related(
            "variant",
            "variant__product",
            "variant__product__subcategory",
            "variant__product__subcategory__category",
            "variant__color",
            "variant__age_group",
        )
        .filter(
            variant__product__is_deleted=False,
            variant__product__is_active=True,
            variant__product__subcategory__is_deleted=False,
            variant__product__subcategory__category__is_deleted=False,
        )
        .order_by(order_field)
    )

    # search — same logic as original
    if search:
        inventories = (
            inventories.filter(variant__product__product_name__icontains=search)
            | inventories.filter(variant__sku__icontains=search)
            | inventories.filter(variant__product__brand__icontains=search)
        )

    # ADD-ON: filter by stock level when the toolbar dropdown is used
    if stock_f == "out":
        inventories = inventories.filter(quantity_available=0)
    elif stock_f == "low":
        inventories = inventories.filter(
            quantity_available__gt=0, quantity_available__lte=5
        )

    page_obj = paginate_queryset(request, inventories, 20)

    return render(
        request,
        "products/admin/admin_inventory_list.html",
        {
            "inventories": page_obj,   # key name unchanged
            "page_obj":    page_obj,
            "search":      search,
            # ADD-ON: pass state back so toolbar stays in sync across pages
            "sort":        sort,
            "stock_f":     stock_f,
        },
    )



@never_cache
@admin_login_required
@transaction.atomic
def update_stock(request, inventory_id):   # inventory_id is now passed as a parameter
    inventory = get_object_or_404(Inventory, id=inventory_id)  # fetch the inventory record based on the provided ID

    if request.method == "POST":
        try:
            change = int(request.POST.get("quantity", 0))
        except (ValueError, TypeError):
            messages.error(request, "Invalid quantity.")
            return redirect("products:admin_inventory_list")

        action = request.POST.get("action", "add")

        if action == "remove":
            if change > inventory.quantity_available:
                messages.error(request, "Not enough stock available.")
                return redirect("products:admin_inventory_list")
            inventory.quantity_available -= change
        else:
            inventory.quantity_available += change

        inventory.save()
        messages.success(request, f"Stock updated for {inventory.variant}.")

    return redirect("products:admin_inventory_list")


def sync_inventory(variant: ProductVariant, delta_available=0, delta_reserved=0, delta_sold=0):
    inventory, _ = Inventory.objects.get_or_create(
        variant=variant, defaults={"quantity_available": 0}
    )
    inventory.quantity_available += delta_available
    inventory.quantity_reserved += delta_reserved
    inventory.quantity_sold += delta_sold
    inventory.save()