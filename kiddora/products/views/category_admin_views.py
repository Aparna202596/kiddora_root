from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.contrib import messages
from django.views.decorators.cache import never_cache
from products.models import *
from accounts.decorators import admin_login_required

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
