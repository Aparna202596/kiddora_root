from django.views.decorators.cache import never_cache
from django.core.paginator import Paginator
from accounts.decorators import admin_login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
import os

from products.models import Category, SubCategory, Product, ProductVariant

#   =============================================== CATEGORY MANAGEMENT ===============================================

#   ────────────────────────────────────────────────── CATEGORY LIST ──────────────────────────────────────────────────
@never_cache
@admin_login_required
def admin_category_list(request):
    search = request.GET.get("search", "").strip()
    sort = request.GET.get("sort", "id")
    direction = request.GET.get("dir", "desc")

    categories = Category.objects.filter(is_deleted=False)
    if search:
        categories = categories.filter(category_name__icontains=search)

    allowed_sorts = ["id", "category_name"]
    if sort not in allowed_sorts:
        sort = "id"
    order_by = sort if direction == "asc" else f"-{sort}"
    categories = categories.order_by(order_by)

    paginator = Paginator(categories, 15)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(request, "products/admin/admin_category_list.html", {
        "page_obj": page_obj,
        "search": search,
        "sort": sort,
        "dir": direction,
    })

#   ────────────────────────────────────────────────── ADD CATEGORY ──────────────────────────────────────────────────
@never_cache
@admin_login_required
def admin_add_category(request):
    if request.method == "POST":
        name = request.POST.get("category_name", "").strip()
        subcategory_name = request.POST.get("subcategory_name", "").strip()
        category_image = request.FILES.get("category_image")

        if Category.objects.filter(category_name__iexact=name, is_active=True).exists():
            messages.error(request, "Category already exists")
            return redirect("products:admin_add_category")
        
        category = Category.objects.create(category_name=name, category_image=category_image)

        if subcategory_name:
            SubCategory.objects.create(category=category, subcategory_name=subcategory_name)

        messages.success(request, "Category added successfully")
        return redirect("products:admin_category_list")

    categories = Category.objects.filter(is_active=True)
    return render(request, "products/admin/admin_category_form.html", {"categories": categories})

#   ────────────────────────────────────────────────── EDIT CATEGORY ──────────────────────────────────────────────────
@never_cache
@admin_login_required
def admin_edit_category(request, category_id):
    category   = get_object_or_404(Category, id=category_id, is_active=True)
    categories = Category.objects.filter(is_active=True)

    if request.method == "POST":
        category_name = request.POST.get("category_name", "").strip()
        new_image = request.FILES.get("category_image")

        if Category.objects.filter(
            category_name__iexact=category_name
        ).exclude(id=category.id).exists():
            messages.error(request, "Category with this name already exists.")
            return redirect("products:admin_edit_category", category_id=category.id)

        category.category_name = category_name

        if new_image:
            if category.category_image:
                try:
                    old_path = category.category_image.path
                    if os.path.isfile(old_path):
                        os.remove(old_path)
                except Exception:
                    pass
            category.category_image = new_image

        category.save()
        messages.success(request, "Category updated")
        return redirect("products:admin_category_list")

    return render(request, "products/admin/admin_category_form.html", {
        "category":   category,
        "categories": categories,
    })

#   ────────────────────────────────────────────────── DELETE CATEGORY ──────────────────────────────────────────────────
@never_cache
@admin_login_required
def admin_delete_category(request, category_id):
    category = get_object_or_404(Category, id=category_id)
    category.is_deleted = True
    category.is_active  = False
    category.save()
    SubCategory.objects.filter(category=category).update(is_deleted=True, is_active=False)
    Product.objects.filter(subcategory__category=category).update(is_active=False, is_deleted=True)
    ProductVariant.objects.filter(product__subcategory__category=category).update(is_active=False)
    messages.success(request, "Category deleted safely")
    return redirect("products:admin_category_list")

#   ────────────────────────────────────────────────── BLOCK CATEGORY ──────────────────────────────────────────────────
@never_cache
@admin_login_required
def admin_block_category(request, category_id):
    category = get_object_or_404(Category, id=category_id)
    if request.method == "POST":
        category.is_active = False
        category.save()
        SubCategory.objects.filter(category=category).update(is_active=False)
        Product.objects.filter(subcategory__category=category).update(is_active=False)
        ProductVariant.objects.filter(product__subcategory__category=category).update(is_active=False)
        messages.success(request, f"{category.category_name} and its subcategories have been blocked.")
        return redirect("products:admin_category_list")
    return render(request, "admin_confirm_block.html", {"category": category})

#   ────────────────────────────────────────────────── UNBLOCK CATEGORY ──────────────────────────────────────────────────
@never_cache
@admin_login_required
def admin_unblock_category(request, category_id):
    category = get_object_or_404(Category, id=category_id)
    if request.method == "POST":
        category.is_active = True
        category.save()
        SubCategory.objects.filter(category=category, is_deleted=False).update(is_active=True)
        Product.objects.filter(subcategory__category=category, is_deleted=False).update(is_active=True)
        ProductVariant.objects.filter(
            product__subcategory__category=category, product__is_deleted=False
        ).update(is_active=True)
        messages.success(request, f"{category.category_name} and all its children have been unblocked.")
        return redirect("products:admin_category_list")
    return render(request, "admin_confirm_unblock.html", {"category": category})



#   =============================================== SUBCATEGORY MANAGEMENT ===============================================

#   ────────────────────────────────────────────────── SUBCATEGORY LIST ──────────────────────────────────────────────────
@never_cache
@admin_login_required
def admin_subcategory_list(request):
    search = request.GET.get("search", "").strip()
    sort = request.GET.get("sort", "id")
    direction = request.GET.get("dir", "desc")

    subcategories = SubCategory.objects.filter(is_deleted=False, category__is_deleted=False).select_related("category")

    if search:
        subcategories = subcategories.filter(subcategory_name__icontains=search)

    allowed_sorts = ["id", "subcategory_name", "category__category_name"]
    if sort not in allowed_sorts:
        sort = "id"
    order_by = sort if direction == "asc" else f"-{sort}"
    subcategories = subcategories.order_by(order_by)

    paginator = Paginator(subcategories, 15)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(request, "products/admin/admin_subcategory_list.html", {
        "page_obj": page_obj,
        "search": search,
        "sort": sort,
        "dir": direction,
    })

#   ────────────────────────────────────────────────── ADD SUBCATEGORY ──────────────────────────────────────────────────
@never_cache
@admin_login_required
def admin_add_subcategory(request):
    categories = Category.objects.filter(is_active=True)

    if request.method == "POST":
        name = request.POST.get("subcategory_name", "").strip()
        category_id = request.POST.get("category")
        subcategory_image = request.FILES.get("subcategory_image")

        category = get_object_or_404(Category, id=category_id, is_active=True)

        if SubCategory.objects.filter(
            category=category, subcategory_name__iexact=name).exists():
            messages.error(request, "SubCategory already exists in this category")
            return redirect("products:admin_add_subcategory")

        SubCategory.objects.create(category=category, subcategory_name=name, subcategory_image=subcategory_image)

        messages.success(request, "SubCategory added")
        return redirect("products:admin_subcategory_list")

    return render(request, "products/admin/admin_subcategory_form.html", {"categories": categories})

#   ────────────────────────────────────────────────── EDIT SUBCATEGORY ──────────────────────────────────────────────────
@never_cache
@admin_login_required
def admin_edit_subcategory(request, subcategory_id):
    subcategory = get_object_or_404(SubCategory, id=subcategory_id)
    categories  = Category.objects.filter(is_active=True)

    if request.method == "POST":
        name = request.POST.get("subcategory_name", "").strip()
        category_id = request.POST.get("category")
        new_image   = request.FILES.get("subcategory_image")

        category = get_object_or_404(Category, id=category_id, is_active=True)

        if SubCategory.objects.filter(
            category=category, subcategory_name__iexact=name
        ).exclude(id=subcategory.id).exists():
            messages.error(request, "Duplicate SubCategory in this category")
            return redirect("products:admin_edit_subcategory", subcategory_id=subcategory.id)

        subcategory.subcategory_name = name
        subcategory.category = category

        if new_image:
            if subcategory.subcategory_image:
                try:
                    old_path = subcategory.subcategory_image.path
                    if os.path.isfile(old_path):
                        os.remove(old_path)
                except Exception:
                    pass

            subcategory.subcategory_image = new_image

        subcategory.save()
        messages.success(request, "SubCategory updated")
        return redirect("products:admin_subcategory_list")

    return render(request, "products/admin/admin_subcategory_form.html", {
        "subcategory": subcategory,
        "categories": categories,
    })

#   ────────────────────────────────────────────────── DELETE SUBCATEGORY ──────────────────────────────────────────────────
@never_cache
@admin_login_required
def admin_delete_subcategory(request, subcategory_id):
    subcategory = get_object_or_404(SubCategory, id=subcategory_id)
    subcategory.is_deleted = True
    subcategory.is_active = False
    subcategory.save()

    Product.objects.filter(subcategory=subcategory).update(is_active=False, is_deleted=True)
    ProductVariant.objects.filter(product__subcategory=subcategory).update(is_active=False)
    messages.success(request, "SubCategory deleted safely")
    return redirect("products:admin_subcategory_list")

#   ────────────────────────────────────────────────── BLOCK SUBCATEGORY ──────────────────────────────────────────────────
@never_cache
@admin_login_required
def admin_block_subcategory(request, subcategory_id):
    subcategory = get_object_or_404(SubCategory, id=subcategory_id)
    if request.method == "POST":
        subcategory.is_active = False
        subcategory.save()
        Product.objects.filter(subcategory=subcategory).update(is_active=False)
        ProductVariant.objects.filter(product__subcategory=subcategory).update(is_active=False)
        messages.success(request, f"{subcategory.subcategory_name} and its products have been blocked.")
        return redirect("products:admin_subcategory_list")
    return render(request, "admin_confirm_block.html", {"subcategory": subcategory})

#   ────────────────────────────────────────────────── UNBLOCK SUBCATEGORY ──────────────────────────────────────────────────
@never_cache
@admin_login_required
def admin_unblock_subcategory(request, subcategory_id):
    subcategory = get_object_or_404(SubCategory, id=subcategory_id)
    if request.method == "POST":
        if not subcategory.category.is_active or subcategory.category.is_deleted:
            messages.error(
                request,
                f"Cannot unblock '{subcategory.subcategory_name}' because its category "
                f"'{subcategory.category.category_name}' is blocked. Unblock the category first."
            )
            return redirect("products:admin_subcategory_list")
        subcategory.is_active = True
        subcategory.save()
        Product.objects.filter(subcategory=subcategory, is_deleted=False).update(is_active=True)
        ProductVariant.objects.filter(
            product__subcategory=subcategory, product__is_deleted=False
        ).update(is_active=True)
        messages.success(request, f"{subcategory.subcategory_name} and its products have been unblocked.")
        return redirect("products:admin_subcategory_list")
    return render(request, "admin_confirm_unblock.html", {"subcategory": subcategory})