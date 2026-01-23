from django.shortcuts import render, get_object_or_404
from products.models import Category, SubCategory, Product

# Category listing page
def category_list_view(request):
    categories = Category.objects.filter(is_active=True).order_by("category_name")
    return render(request, "products/catalog/category_list.html", {"categories": categories})

# SubCategory listing page
def subcategory_list_view(request, category_id):
    category = get_object_or_404(Category, id=category_id, is_active=True)
    subcategories = category.subcategories.filter(category=category)
    return render(
        request,
        "products/catalog/subcategory_list.html",
        {"category": category, "subcategories": subcategories}
    )

