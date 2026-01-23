from django.shortcuts import render
from products.models import Product
from django.db.models import Q

def product_search_view(request):
    query = request.GET.get("q", "")
    products = Product.objects.filter(is_active=True)
    if query:
        products = products.filter(
            Q(product_name__icontains=query) |
            Q(brand__icontains=query) |
            Q(subcategory__subcategory_name__icontains=query) |
            Q(subcategory__category__category_name__icontains=query)
        )
    return render(
        request,
        "products/search/product_search.html",
        {"products": products, "query": query}
    )
