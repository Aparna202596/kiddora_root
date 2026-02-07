from itertools import product
from urllib import request
from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.contrib import messages
from django.utils import timezone
from django.views.decorators.cache import never_cache
from products.models import Category, Product, ProductImage, AgeGroup, ProductVariant, Inventory, SubCategory, Offer
from accounts.decorators import admin_login_required
from products.services.inventory import reserve_stock, release_stock

# CATEGORY MANAGEMENT

@admin_login_required
def admin_category_list(request):
    search = request.GET.get("search", "").strip()
    sort = request.GET.get("sort", "id")
    direction = request.GET.get("dir", "desc")

    categories = Category.objects.filter(is_active=True)

    if search:
        categories = categories.filter(category_name__icontains=search)

    allowed_sorts = ["id", "category_name"]
    if sort not in allowed_sorts:
        sort = "id"

    order_by = sort if direction == "asc" else f"-{sort}"
    categories = categories.order_by(order_by)

    paginator = Paginator(categories, 15)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "products/admin/admin_category_list.html",
        {
            "page_obj": page_obj,
            "search": search,
            "sort": sort,
            "dir": direction,
        },)

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
        if Category.objects.filter(category_name__iexact=category_name).exclude(id=category.id).exists():
            messages.error(request, "Category with this name already exists.")
            return redirect("products:admin_edit_category", category_id=category.id)
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
    sort = request.GET.get("sort", "id")
    direction = request.GET.get("dir", "desc")

    subcategories = SubCategory.objects.filter(category__is_active=True).select_related("category")

    if search:
        subcategories = subcategories.filter(subcategory_name__icontains=search)

    allowed_sorts = ["id", "subcategory_name", "category__category_name"]
    if sort not in allowed_sorts:
        sort = "id"

    order_by = sort if direction == "asc" else f"-{sort}"
    subcategories = subcategories.order_by(order_by)

    paginator = Paginator(subcategories, 15)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "products/admin/admin_subcategory_list.html",
        {
            "page_obj": page_obj,
            "search": search,
            "sort": sort,
            "dir": direction,
        },
    )

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
    sort = request.GET.get("sort", "id")
    direction = request.GET.get("dir", "desc")

    products = Product.objects.filter(is_active=True).select_related(
        "subcategory", "subcategory__category"
    )

    if search:
        products = products.filter(
            Q(product_name__icontains=search)
            | Q(brand__icontains=search)
            | Q(sku__icontains=search)
        )

    allowed_sorts = [
        "id",
        "product_name",
        "brand",
        "final_price",
        "subcategory__subcategory_name",
        "subcategory__category__category_name",
        "gender",
    ]

    if sort not in allowed_sorts:
        sort = "id"

    order_by = sort if direction == "asc" else f"-{sort}"
    products = products.order_by(order_by)

    paginator = Paginator(products, 15)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "products/admin/admin_product_list.html",
        {
            "page_obj": page_obj,
            "search": search,
            "sort": sort,
            "dir": direction,
        },
    )

# ---------- ADD PRODUCT ----------
@admin_login_required
def admin_add_product(request):
    categories = Category.objects.filter(is_active=True)
    subcategories = SubCategory.objects.filter(category__is_active=True)
    brands = Product.objects.values_list("brand", flat=True).distinct()
    age_group = AgeGroup.objects.all()

    if request.method == "POST":
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

        sku_from_form = request.POST.get("sku")
        if sku_from_form:
            # Optional: check uniqueness
            if Product.objects.filter(sku=sku_from_form).exists():
                messages.error(request, f"SKU {sku_from_form} already exists.")
                return redirect("products:admin_add_product")
            sku_value = sku_from_form
        else:
            sku_value = None  # triggers auto-generation in save()

        product = Product.objects.create(
            subcategory=subcategory,
            product_name=request.POST.get("product_name"),
            brand=request.POST.get("brand"),
            gender=request.POST.get("gender", "unisex"),
            base_price=base_price,
            discount_percent=discount_percent,
            final_price=final_price,
            sku=sku_value,
            fabric=request.POST.get("fabric", "Other"),               
            about_product=request.POST.get("about_product", ""),     
            is_active=True,
        )
        age_ids = request.POST.getlist("age_group")
        product.age_group.set(age_ids)

        images = request.FILES.getlist('product_images')
        if len(images) < 2:
            product.delete() # delete the product we just created to avoid incomplete entry
            messages.error(request, "At least 2 product images are required.")
            return redirect("products:admin_add_product")

        for i, img in enumerate(images):
            ProductImage.objects.create(product=product,image=img,is_default=(i == 0))
        
        # Product Variants
        colors = [c.strip() for c in request.POST.get("colors", "").split(",") if c.strip()]
        sizes = request.POST.getlist("sizes")

        for color in colors:
            for size in sizes:
                ProductVariant.objects.create(
                    product=product,
                    color=color,
                    size=size,
                    barcode=f"{product.sku}-{color}-{size}".upper(),
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
            "AGE_GROUPS": age_group,
            "SIZE_CHOICES": ProductVariant.SIZE_CHOICES,
            "GENDER_CHOICES": Product.GENDER_CHOICES,
            "FABRIC_CHOICES": Product.FABRIC_CHOICES,
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

        sku_from_form = request.POST.get("sku")
        if sku_from_form and sku_from_form != product.sku:
            if Product.objects.filter(sku=sku_from_form).exists():
                messages.error(request, f"SKU {sku_from_form} already exists.")
                return redirect(request.path)
            product.sku = sku_from_form
        # ---- UPDATE PRODUCT ----
        product.product_name = request.POST.get("product_name")
        product.brand = request.POST.get("brand")
        product.gender = request.POST.get("gender", "unisex")
        product.age_group = request.POST.get("age_group", Product.AGE_CHOICES[0][0])
        product.base_price = base_price
        product.discount_percent = discount_percent
        product.final_price = final_price
        product.sku = request.POST.get("sku")
        product.fabric = request.POST.get("fabric", "Other")           
        product.about_product = request.POST.get("about_product", "")
        product.stock = request.POST.get("stock", product.stock) 
        # product.stock = request.POST.get("stock", 0)
        product.is_active = bool(request.POST.get("is_active"))
        product.subcategory_id = request.POST.get("subcategory")
        product.save()

        # ---- HANDLE PRODUCT IMAGES ----
        images = request.FILES.getlist('product_images')
        if images:
            if len(images) < 3:
                messages.error(request, "At least 3 product images are required.")
                return redirect(request.path)

            # Delete old images only if new images are uploaded
            ProductImage.objects.filter(product=product).delete()
            for img in images:
                ProductImage.objects.create(product=product, image=img)
        
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
            "FABRIC_CHOICES": Product.FABRIC_CHOICES,
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



