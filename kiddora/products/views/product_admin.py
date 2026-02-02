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
AGE_CHOICES = [
    "0-6 months",
    "6-12 months",
    "1-2 years",
    "2-3 years",
    "3-5 years",
    "5-7 years",
    "7-10 years",
    "10-15 years",
]

SIZE_CHOICES = ["XS", "S", "M", "L", "XL"]

@admin_login_required
def admin_product_list(request):
    search = request.GET.get("search", "").strip()
    products = Product.objects.filter(is_active=True)

    if search:
        products = products.filter(Q(product_name__icontains=search) | Q(brand__icontains=search))

    products = products.order_by("-id")
    paginator = Paginator(products, 10)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(request, "products/admin/admin_product_list.html", {"page_obj": page_obj, "search": search})

@admin_login_required
def admin_add_product(request):
    categories = Category.objects.filter(is_active=True)
    subcategories = SubCategory.objects.filter(category__is_active=True)

    if request.method == "POST":
        subcategory = get_object_or_404(SubCategory, id=request.POST.get("subcategory"))
        product = Product.objects.create(
            subcategory=subcategory,
            product_name=request.POST.get("product_name"),
            brand=request.POST.get("brand"),
            base_price=request.POST.get("base_price"),
            final_price=request.POST.get("final_price"),
            discount_percent=request.POST.get("discount", 0),
            sku=request.POST.get("sku"),
            is_active=True,
        )

        # Product Variants
        colors = request.POST.getlist("colors")

        for color in colors:
            for age in AGE_CHOICES:
                for size in SIZE_CHOICES:
                    ProductVariant.objects.create(
                        product=product,
                        color=f"{color} | {age}",
                        size=size,
                        barcode=f"{product.sku}-{color}-{age}-{size}".replace(" ", "").upper(),
                    )

        messages.success(request, "Product added successfully")
        return redirect("products:admin_product_list")

    return render(request, "products/admin/admin_product_form.html", {"categories": categories, "subcategories": subcategories})

@admin_login_required
def admin_edit_product(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    subcategories = SubCategory.objects.filter(category__is_active=True)

    if request.method == "POST":
        product.product_name = request.POST.get("product_name")
        product.brand = request.POST.get("brand")
        product.base_price = request.POST.get("base_price")
        product.final_price = request.POST.get("final_price")
        product.discount_percent = request.POST.get("discount", 0)
        product.sku = request.POST.get("sku")
        product.is_active = bool(request.POST.get("is_active"))
        product.subcategory_id = request.POST.get("subcategory")
        product.save()

        # Update variants (optional: delete old & create new or update)
        ProductVariant.objects.filter(product=product).delete()
        colors = request.POST.getlist("colors")
        for color in colors:
            for age in AGE_CHOICES:
                for size in SIZE_CHOICES:
                    ProductVariant.objects.create(
                        product=product,
                        color=f"{color} | {age}",
                        size=size,
                        barcode=f"{product.sku}-{color}-{age}-{size}".replace(" ", "").upper(),
                    )

        messages.success(request, "Product updated")
        return redirect("products:admin_product_list")

    return render(request, "products/admin/admin_product_form.html", {"product": product, "subcategories": subcategories})

@admin_login_required
def admin_delete_product(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    product.is_active = False  # soft delete
    product.save()
    messages.success(request, "Product deleted safely")
    return redirect("products:admin_product_list")

@admin_login_required
def admin_product_details(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    variants = product.variants.filter(is_active=True)

    return render(
        request,
        "products/admin/admin_product_details.html",
        {
            "product": product,
            "variants": variants,
        },
    )

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



