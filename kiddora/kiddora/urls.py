"""
URL configuration for kiddora project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect

urlpatterns=[
    path('admin/', admin.site.urls),

    path('accounts/', include('accounts.urls')),
    path('products/', include('products.urls')),
    path('cart/', include('cart.urls')),
    path('orders/',include('orders.urls')),
    path('payments/',include('payments.urls')),
    path('returns/',include('returns.urls')),
    path('reviews/',include('reviews.urls')),
    path('store/',include('store.urls')),
    path('wallet/',include('wallet.urls')),
    path('wishlist/',include('wishlist.urls')),
    # Root URL → anonymous home page
    path('', lambda request: redirect('store:anonymous_user_home'), name='root_redirect'),
    ]
    
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

