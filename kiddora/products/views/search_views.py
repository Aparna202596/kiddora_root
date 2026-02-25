from django.shortcuts import render
from products.models import *
from django.db.models import Q

def search_products(request):
    query = request.GET.get("q", "")
    products = Product.objects.filter(is_active=True)
    if query:
        products = products.filter(
            Q(product_name__icontains=query) |
            Q(brand__icontains=query) |
            Q(subcategory__subcategory_name__icontains=query) |
            Q(subcategory__category__category_name__icontains=query)
        )
    
    context={{"products": products, "query": query}}
    return render(request,"products/search/search_results.html",context)
