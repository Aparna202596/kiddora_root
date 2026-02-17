from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.views.decorators.cache import never_cache
from django.db import transaction
from products.models import (
    Product, ProductImage, ProductVariant, Inventory,
    Category, SubCategory, AgeGroup, Color
)
from accounts.decorators import admin_login_required

# ---------- MANDATORY UTILITIES (do not modify) ----------
from utils.image_utils import validate_image, resize_image, crop_image, process_profile_image,validate_product_image,process_image
from products.utils.pagination import paginate_queryset
from products.utils.queryset_utils import apply_product_filters, apply_sorting
from products.utils.search_utils import apply_search

from django.http import JsonResponse
from utils.image_utils import process_product_image
import json
# ======================================================
# 1) PRODUCT LISTING — Search + Filter + Sort + Pagination
# ======================================================
@never_cache
@admin_login_required
def admin_product_list(request):
    search = request.GET.get("search", "").strip()
    sort = request.GET.get("sort", "new")
    category_id = request.GET.get("category")
    subcategory_id = request.GET.get("subcategory")

    products = (
        Product.objects
        .filter(is_active=True)
        .select_related("subcategory", "subcategory__category")
        .prefetch_related("variants", "images")
    )

    # Search across product_name, brand, sku
    products = apply_search(products, search, ["product_name", "brand", "sku"])

    # Category / Subcategory filters
    products = apply_product_filters(
        products,
        category_id=category_id,
        subcategory_id=subcategory_id
    )

    # Sorting map
    sort_map = {
        "price_low": "final_price",
        "price_high": "-final_price",
        "az": "product_name",
        "za": "-product_name",
        "new": "-id",
        # placeholders if future fields added:
        "popular": "-total_sold",   # hypothetical
        "rating": "-avg_rating",    # hypothetical
    }
    products = apply_sorting(products, sort, sort_map, default="-id")

    # Pagination (10 per page)
    page_obj = paginate_queryset(request, products, per_page=10)

    return render(
        request,
        "products/admin/admin_product_list.html",
        {
            "page_obj": page_obj,
            "search": search,
            "sort": sort,
            "categories": Category.objects.filter(is_active=True),
            "subcategories": SubCategory.objects.filter(category__is_active=True),
        }
    )


# ======================================================
# 2) PRODUCT DETAIL (ADMIN VIEW)
# ======================================================
@never_cache
@admin_login_required
def admin_product_details(request, product_id):
    product = get_object_or_404(Product, id=product_id)

    # Redirect / block if product inactive
    if not product.is_active:
        messages.error(request, "This product is blocked or unavailable.")
        return redirect("products:admin_product_list")

    return render(
        request,
        "products/admin/admin_product_detail.html",
        {
            "product": product,
            "images": product.images.all(),
            "variants": product.variants.filter(is_active=True),
        }
    )


# ======================================================
# 3) ADD PRODUCT
# ======================================================
@never_cache
@admin_login_required
@transaction.atomic
def admin_add_product(request):
    # Data for form dropdowns / checkboxes
    categories = Category.objects.filter(is_active=True)
    subcategories = SubCategory.objects.filter(category__is_active=True)
    age_groups = AgeGroup.objects.all()
    colors = Color.objects.all()

    if request.method == "POST":
        # Validate image count
        images = request.FILES.getlist("product_images")
        if len(images) < 3:
            messages.error(request, "Minimum 3 images are required.")
            return redirect("products:admin_add_product")

        # Create product
        product = Product.objects.create(
            product_name=request.POST.get("product_name").strip(),
            brand=request.POST.get("brand").strip(),
            subcategory=get_object_or_404(
                SubCategory, id=request.POST.get("subcategory")
            ),
            gender=request.POST.get("gender"),
            fabric=request.POST.get("fabric"),
            base_price=request.POST.get("base_price"),
            discount_percent=request.POST.get("discount_percent"),
            stock=request.POST.get("stock"),
            about_product=request.POST.get("about_product").strip(),
        )
        # final_price automatically calculated in Product.save()

        # Save images (processed) and set first as default
        for idx, img in enumerate(images):
            processed = process_image(img)
            ProductImage.objects.create(
                product=product,
                image=processed,
                is_default=(idx == 0)
            )

        # Create one variant for initial ages/colors
        variant = ProductVariant.objects.create(
            product=product,
            barcode=f"{product.sku}-VAR1"
        )
        variant.ages.set(
            AgeGroup.objects.filter(id__in=request.POST.getlist("ages"))
        )
        variant.colors.set(
            Color.objects.filter(id__in=request.POST.getlist("colors"))
        )

        # Inventory synced to product stock
        Inventory.objects.create(
            variant=variant,
            quantity_available=product.stock
        )

        messages.success(request, "Product added successfully.")
        return redirect("products:admin_product_list")

    # GET: render form
    return render(
        request,
        "products/admin/admin_product_form.html",
        {
            "categories": categories,
            "subcategories": subcategories,
            "age_groups": age_groups,
            "colors": colors,
        }
    )


# ======================================================
# 4) EDIT PRODUCT
# ======================================================
@never_cache
@admin_login_required
@transaction.atomic
def admin_edit_product(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    variant = product.variants.first()

    categories = Category.objects.filter(is_active=True)
    subcategories = SubCategory.objects.filter(category__is_active=True)
    age_groups = AgeGroup.objects.all()
    colors = Color.objects.all()

    # Pre-selected ages and colors if variant exists
    selected_ages = variant.ages.values_list("id", flat=True) if variant else []
    selected_colors = variant.colors.values_list("id", flat=True) if variant else []

    if request.method == "POST":
        # Update product fields
        product.product_name = request.POST.get("product_name").strip()
        product.brand = request.POST.get("brand").strip()
        product.subcategory_id = request.POST.get("subcategory")
        product.gender = request.POST.get("gender")
        product.fabric = request.POST.get("fabric")
        product.base_price = request.POST.get("base_price")
        product.discount_percent = request.POST.get("discount_percent")
        product.stock = request.POST.get("stock")
        product.about_product = request.POST.get("about_product").strip()
        product.save()  # final_price recalculated in save()

        # Append any new images
        for img in request.FILES.getlist("product_images"):
            processed = process_image(img)
            ProductImage.objects.create(product=product, image=processed)

        # Update variant ages / colors
        if variant:
            variant.ages.set(
                AgeGroup.objects.filter(id__in=request.POST.getlist("ages"))
            )
            variant.colors.set(
                Color.objects.filter(id__in=request.POST.getlist("colors"))
            )

            # Sync inventory to new stock
            inventory = getattr(variant, "inventory", None)
            if inventory:
                inventory.quantity_available = product.stock
                inventory.save()

        messages.success(request, "Product updated successfully.")
        return redirect("products:admin_product_list")

    # GET: render form with existing data
    return render(
        request,
        "products/admin/admin_product_form.html",
        {
            "product": product,
            "variant": variant,
            "categories": categories,
            "subcategories": subcategories,
            "age_groups": age_groups,
            "colors": colors,
            "selected_ages": selected_ages,
            "selected_colors": selected_colors,
        }
    )


# ======================================================
# 5) DELETE PRODUCT — Soft delete
# ======================================================
@admin_login_required
def admin_delete_product(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    product.is_active = False
    product.save()

    # Also block variants
    product.variants.update(is_active=False)

    messages.success(request, "Product blocked successfully.")
    return redirect("products:admin_product_list")

def ajax_product_image_upload(request):
    image = request.FILES.get("image")
    crop_data = json.loads(request.POST.get("crop_data", "{}"))

    processed = process_product_image(image, crop_data)
    return JsonResponse({"status": "success"})