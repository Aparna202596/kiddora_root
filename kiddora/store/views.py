
from django.shortcuts import render
from django.contrib.auth import get_user_model
from django.views.decorators.cache import never_cache
from accounts.decorators import user_login_required
from products.models import Category, Product

User = get_user_model()

def anonymous_home(request):
    categories = Category.objects.filter(is_active=True)
    products = Product.objects.filter(is_active=True).order_by('-id')[:8]
    return render(request, 'store/anonymous_home.html', {
        'categories': categories,
        'products': products
    })
@never_cache
@user_login_required
def home(request):
    categories = Category.objects.filter(is_active=True)
    products = Product.objects.filter(
        is_active=True,
        subcategory__category__is_active=True,).order_by('-id')[:12]
    return render(request, 'store/home.html', {
        'categories': categories,
        'products': products
    })

def aboutus_view(request):
    return render(request, 'store/about_us.html')

def contactus_view(request):
    return render(request, 'store/contact_us.html')

def privacy_policy_view(request):
    return render(request, 'store/privacy_policy.html')

def terms_conditions_view(request):
    return render(request, 'store/terms_conditions.html')

def return_policy_view(request):
    return render(request, 'store/return_policy.html')

def cookie_policy_view(request):
    return render(request, 'store/cookie_policy.html')

def blog_view(request):
    return render(request, 'store/blog.html')