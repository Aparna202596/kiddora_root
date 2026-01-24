from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.contrib import messages
from django.utils import timezone
from django.views.decorators.cache import never_cache
from products.models import Category, Product, ProductVariant, Inventory, SubCategory, Offer
from accounts.decorators import admin_login_required
from products.services.inventory import reserve_stock, release_stock

@admin_login_required
def admin_category_list(request):
    search = request.GET.get("search", "").strip()
    categories = Category.objects.filter(is_deleted=False)
    if search:
        categories = categories.filter(category_name__icontains=search)

    categories = categories.order_by("-id")
    paginator = Paginator(categories, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    context={"page_obj": page_obj,"search": search,}
    return render(request, "products/admin/admin_category_list.html", context)

@admin_login_required
def admin_add_category(request):
    if request.method == "POST":
        name = request.POST.get("category_name").strip()

        if Category.objects.filter(category_name__iexact=name, is_deleted=False).exists():
            messages.error(request, "Category already exists")
            return redirect("products:admin_add_category")
        Category.objects.create(category_name=name)
        messages.success(request, "Category added successfully")
        return redirect("products:admin_category_list")
    return render(request, "products/admin/admin_category_form.html")

@admin_login_required
def admin_edit_category(request, category_id):
    category = get_object_or_404(Category, id=category_id, is_deleted=False)

    if request.method == "POST":
        category.category_name = request.POST.get("category_name").strip()
        category.is_active = request.POST.get("is_active") == "on"
        category.save()
        messages.success(request, "Category updated")
        return redirect("products:admin_category_list")
    return render(request, "products/admin/admin_category_form.html", {"category": category})

@admin_login_required
def admin_delete_category(request, category_id):
    category = get_object_or_404(Category, id=category_id)
    category.is_deleted = True
    category.is_active = False
    category.save()

    Product.objects.filter(subcategory__category=category).update(is_active=False)
    messages.success(request, "Category deleted safely")
    return redirect("products:admin_category_list")

@admin_login_required
def admin_product_list(request):
    search = request.GET.get("search", "").strip()
    products = Product.objects.all()
    if search:
        products = products.filter(
            Q(product_name__icontains=search) |
            Q(brand__icontains=search)
        )
    products = products.order_by("-id")
    paginator = Paginator(products, 10)
    page_obj = paginator.get_page(request.GET.get("page"))
    context=  {
        "page_obj": page_obj,
        "search": search,
    }
    return render(request, "products/admin/admin_product_list.html",context)

@admin_login_required
def admin_add_product(request):
    categories = Category.objects.filter(is_active=True, is_deleted=False)

    if request.method == "POST":
        subcategory = SubCategory.objects.get(id=request.POST.get("subcategory"))
        product = Product.objects.create(
            subcategory=subcategory,
            product_name=request.POST["product_name"],
            brand=request.POST["brand"],
            subcategory_id=request.POST["subcategory"],
            base_price=request.POST["base_price"],
            final_price=request.POST.get("final_price"),
            discount_percent=request.POST.get("discount", 0),
            final_price=request.POST["final_price"],
            sku=request.POST["sku"],
            is_active=True
        )

        messages.success(request, "Product added")
        return redirect("products:admin_product_list")
    context={"product":product,"categories":categories,}
    return render(request, "products/admin/admin_product_form.html", context)

@admin_login_required
def admin_edit_product(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    subcategories = SubCategory.objects.all()

    if request.method == "POST":
        for field in ["product_name", "brand", "base_price", "final_price", "sku"]:
            setattr(product, field, request.POST[field])
        product.product_name = request.POST.get("product_name")
        product.brand = request.POST.get("brand")
        product.final_price = request.POST.get("final_price")
        product.discount_percent = request.POST.get("discount", 0)
        product.is_active = bool(request.POST.get("is_active"))
        product.subcategory_id = request.POST["subcategory"]
        product.save()

        messages.success(request, "Product updated")
        return redirect("products:admin_product_list")

    return render(request, "products/admin/admin_product_form.html", {
        "product": product,
        "subcategories": subcategories,
    })

@admin_login_required
def admin_delete_product(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    product.is_active = False
    product.save()

    messages.success(request, "Product blocked")
    return redirect("products:admin_product_list")

@admin_login_required
def admin_inventory_list(request):
    inventory = Inventory.objects.select_related("variant", "variant__product")
    return render(request, "products/admin/admin_inventory.html", {
        "inventory": inventory
    })

def admin_update_stock(request, inventory_id):
    inventory = get_object_or_404(Inventory, id=inventory_id)

    if request.method == "POST":
        change = int(request.POST.get("quantity"))
        inventory.quantity_available += change
        inventory.save()
        messages.success(request, "Stock updated")
        return redirect("products:admin_inventory_list")


@admin_login_required
def admin_product_offer(request):
    if request.method == "POST":
        Offer.objects.create(
            offer_type="PRODUCT",
            product_id=request.POST["product"],
            discount_percent=request.POST["discount"],
        )
    return render(request, "products/admin/admin_offer_product.html")

@admin_login_required
def admin_category_offer(request):
    if request.method == "POST":
        Offer.objects.create(
            offer_type="CATEGORY",
            category_id=request.POST["category"],
            discount_percent=request.POST["discount"],
        )
    return render(request, "products/admin/admin_offer_category.html")
