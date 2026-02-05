from itertools import product
from urllib import request
from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.contrib import messages
from django.utils import timezone
from django.views.decorators.cache import never_cache
from products.models import Category, Product, ProductVariant, Inventory, SubCategory, Offer
from accounts.decorators import admin_login_required
from products.services.inventory import reserve_stock, release_stock

# CATEGORY MANAGEMENT

@admin_login_required
def admin_category_list(request):
    search = request.GET.get("search", "").strip()
    categories = Category.objects.filter(is_active=True)

    if search:
        categories = categories.filter(category_name__icontains=search)

    categories = categories.order_by("-id")
    paginator = Paginator(categories, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {"page_obj": page_obj, "search": search}
    return render(request, "products/admin/admin_category_list.html", context)

@admin_login_required
def admin_add_category(request):
    if request.method == "POST":
        name = request.POST.get("category_name").strip()
        subcategory_name = request.POST.get("subcategory_name", "").strip()

        if Category.objects.filter(category_name__iexact=name, is_active=True).exists():
            messages.error(request, "Category already exists")
            return redirect("products:admin_add_category")

        category = Category.objects.create(category_name=name)

        if subcategory_name:
            SubCategory.objects.create(category=category, subcategory_name=subcategory_name)

        messages.success(request, "Category added successfully")
        return redirect("products:admin_category_list")

    categories = Category.objects.filter(is_active=True)
    return render(request, "products/admin/admin_category_form.html", {"categories": categories})

@admin_login_required
def admin_edit_category(request, category_id):
    category = get_object_or_404(Category, id=category_id, is_active=True)

    if request.method == "POST":
        category_name = request.POST.get("category_name").strip()
        category.is_active = bool(request.POST.get("is_active"))
        category.category_name = category_name
        category.save()
        messages.success(request, "Category updated")
        return redirect("products:admin_category_list")

    categories = Category.objects.filter(is_active=True)
    return render(request, "products/admin/admin_category_form.html", {"category": category, "categories": categories})

@admin_login_required
def admin_delete_category(request, category_id):
    category = get_object_or_404(Category, id=category_id)
    category.is_active = False  # soft delete
    category.save()
    Product.objects.filter(subcategory__category=category).update(is_active=False)
    messages.success(request, "Category deleted safely")
    return redirect("products:admin_category_list")

# SUBCATEGORY MANAGEMENT

@admin_login_required
def admin_subcategory_list(request):
    search = request.GET.get("search", "").strip()
    subcategories = SubCategory.objects.filter(category__is_active=True)

    if search:
        subcategories = subcategories.filter(subcategory_name__icontains=search)

    subcategories = subcategories.order_by("-id")
    paginator = Paginator(subcategories, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {"page_obj": page_obj, "search": search}
    return render(request, "products/admin/admin_subcategory_list.html", context)

@admin_login_required
def admin_add_subcategory(request):
    categories = Category.objects.filter(is_active=True)
    if request.method == "POST":
        name = request.POST.get("subcategory_name").strip()
        category_id = request.POST.get("category")
        category = get_object_or_404(Category, id=category_id, is_active=True)

        if SubCategory.objects.filter(category=category, subcategory_name__iexact=name).exists():
            messages.error(request, "SubCategory already exists in this category")
            return redirect("products:admin_add_subcategory")

        SubCategory.objects.create(category=category, subcategory_name=name)
        messages.success(request, "SubCategory added")
        return redirect("products:admin_subcategory_list")

    return render(request, "products/admin/admin_subcategory_form.html", {"categories": categories})

@admin_login_required
def admin_edit_subcategory(request, subcategory_id):
    subcategory = get_object_or_404(SubCategory, id=subcategory_id)
    categories = Category.objects.filter(is_active=True)

    if request.method == "POST":
        name = request.POST.get("subcategory_name").strip()
        category_id = request.POST.get("category")
        category = get_object_or_404(Category, id=category_id, is_active=True)

        if SubCategory.objects.filter(category=category, subcategory_name__iexact=name).exclude(id=subcategory.id).exists():
            messages.error(request, "Duplicate SubCategory in this category")
            return redirect("products:admin_edit_subcategory", subcategory_id=subcategory.id)

        subcategory.subcategory_name = name
        subcategory.category = category
        subcategory.save()
        messages.success(request, "SubCategory updated")
        return redirect("products:admin_subcategory_list")

    return render(request, "products/admin/admin_subcategory_form.html", {"subcategory": subcategory, "categories": categories})

@admin_login_required
def admin_delete_subcategory(request, subcategory_id):
    subcategory = get_object_or_404(SubCategory, id=subcategory_id)
    Product.objects.filter(subcategory=subcategory).update(is_active=False)
    subcategory.delete()  
    messages.success(request, "SubCategory deleted safely")
    return redirect("products:admin_subcategory_list")

# PRODUCT MANAGEMENT
# ---------- PRODUCT LIST ----------
@admin_login_required
def admin_product_list(request):
    search = request.GET.get("search", "").strip()
    products = Product.objects.filter(is_active=True).select_related("subcategory", "subcategory__category")

    if search:
        products = products.filter(
            Q(product_name__icontains=search) |
            Q(brand__icontains=search) |
            Q(sku__icontains=search)
        )


    products = products.order_by("-id")
    paginator = Paginator(products, 10)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "products/admin/admin_product_list.html",
        {"page_obj": page_obj, "search": search,},
    )

# ---------- ADD PRODUCT ----------
@admin_login_required
def admin_add_product(request):
    categories = Category.objects.filter(is_active=True)
    subcategories = SubCategory.objects.filter(category__is_active=True)
    brands = Product.objects.values_list("brand", flat=True).distinct()

    if request.method == "POST":
        subcategory_id = request.POST.get("subcategory")
        subcategory = get_object_or_404(SubCategory, id=request.POST.get("subcategory"))
        base_price = request.POST.get("base_price")
        discount_percent = request.POST.get("discount_percent", 0)

        # Convert to float safely
        try:
            base_price = float(request.POST.get("base_price"))
        except (TypeError, ValueError):
            messages.error(request, "Invalid base price")
            return redirect("products:admin_add_product")

        try:
            discount_percent = float(request.POST.get("discount_percent", 0))
        except (TypeError, ValueError):
            discount_percent = 0

        final_price = base_price * (1 - discount_percent / 100)

        product = Product.objects.create(
            subcategory=subcategory,
            product_name=request.POST.get("product_name"),
            brand=request.POST.get("brand"),
            gender=request.POST.get("gender", "unisex"),
            age_group=request.POST.get("age_group", Product.AGE_CHOICES[0][0]),
            base_price=base_price,
            final_price=final_price,
            discount_percent=discount_percent,
            sku=request.POST.get("sku"),
            # stock=request.POST.get("stock", 0),
            is_active=True,
        )

        # Product Variants
        colors = request.POST.get("colors", "").split(",")
        colors = [c.strip() for c in colors if c.strip()]
        for color in colors:
            for size_code, _ in ProductVariant.SIZE_CHOICES:
                ProductVariant.objects.create(
                    product=product,
                    color=color,
                    size=size_code,
                    barcode=f"{product.sku}-{color}-{size_code}"
                    .replace(" ", "")
                    .upper(),
                )

        messages.success(request, "Product added successfully")
        return redirect("products:admin_product_list")

    return render(
        request,
        "products/admin/admin_product_form.html",
        {
            "categories": categories,
            "subcategories": subcategories,
            "brands": brands,
            "AGE_CHOICES": Product.AGE_CHOICES,
            "GENDER_CHOICES": Product.GENDER_CHOICES,
        },
    )

# ---------- EDIT PRODUCT ----------
@admin_login_required
def admin_edit_product(request, product_id):
    categories = Category.objects.filter(is_active=True)
    product = get_object_or_404(Product, id=product_id)
    subcategories = SubCategory.objects.filter(category__is_active=True)
    brands = Product.objects.values_list("brand", flat=True).distinct()
    if request.method == "POST":
        # ---- PRICE HANDLING ----
        try:
            base_price = float(request.POST.get("base_price"))
        except (TypeError, ValueError):
            messages.error(request, "Invalid base price")
            return redirect(
                "products:admin_edit_product", product_id=product.id
            )

        try:
            discount_percent = float(request.POST.get("discount_percent", 0))
        except (TypeError, ValueError):
            discount_percent = 0

        final_price = base_price * (1 - discount_percent / 100)

        # ---- UPDATE PRODUCT ----
        product.product_name = request.POST.get("product_name")
        product.brand = request.POST.get("brand")
        product.gender = request.POST.get("gender", "unisex")
        product.age_group = request.POST.get(
            "age_group", Product.AGE_CHOICES[0][0]
        )
        product.base_price = base_price
        product.discount_percent = discount_percent
        product.final_price = final_price
        product.sku = request.POST.get("sku")
        # product.stock = request.POST.get("stock", 0)
        product.is_active = bool(request.POST.get("is_active"))
        product.subcategory_id = request.POST.get("subcategory")
        product.save()
        
        # ---- RECREATE VARIANTS ----
        ProductVariant.objects.filter(product=product).delete()

        colors = request.POST.get("colors", "").split(",")
        colors = [c.strip() for c in colors if c.strip()]
        for color in colors:
            for size_code, _ in ProductVariant.SIZE_CHOICES:
                ProductVariant.objects.create(
                    product=product,
                    color=color,
                    size=size_code,
                    barcode=f"{product.sku}-{color}-{size_code}"
                    .replace(" ", "")
                    .upper(),
                )

        messages.success(request, "Product updated successfully")
        return redirect("products:admin_product_list")
    selected_sizes = product.variants.values_list("size", flat=True).distinct()
    return render(
        request,
        "products/admin/admin_product_form.html",
        {   
            "categories": categories,
            "product": product,
            "subcategories": subcategories,
            "brands": brands,
            "AGE_CHOICES": Product.AGE_CHOICES,
            "GENDER_CHOICES": Product.GENDER_CHOICES,
            "selected_sizes": selected_sizes,
        },
    )

# ---------- DELETE PRODUCT (soft delete) ----------
@admin_login_required
def admin_delete_product(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    product.is_active = False
    product.save()
    ProductVariant.objects.filter(product=product).update(is_active=False)
    messages.success(request, "Product deleted successfully")
    return redirect("products:admin_product_list")

# ---------- PRODUCT DETAILS ----------
@admin_login_required
def admin_product_details(request, product_id):
    product = Product.objects.select_related(
        "subcategory", "subcategory__category"
    ).prefetch_related("variants").get(id=product_id)
    variants = product.variants.filter(is_active=True)

    return render(
        request,
        "products/admin/admin_product_details.html",
        {"product": product, "variants": variants},
    )
# INVENTORY MANAGEMENT
@admin_login_required
def admin_inventory_list(request):
    inventory = Inventory.objects.select_related("variant", "variant__product")
    return render(request, "products/admin/admin_inventory.html", {
        "inventory": inventory
    })
# Update stock quantity for a variant
@admin_login_required
def admin_update_stock(request, inventory_id):
    inventory = get_object_or_404(Inventory, id=inventory_id)

    if request.method == "POST":
        change = int(request.POST.get("quantity"))
        inventory.quantity_available += change
        inventory.save()
        messages.success(request, "Stock updated")
        return redirect("products:admin_inventory_list")



