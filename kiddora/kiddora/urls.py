from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.shortcuts import redirect
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("accounts/", include("allauth.urls")),
    path("products/", include("products.urls")),
    path("payments/", include("payments.urls", namespace="payments")),
    path("shop/", include("shopcore.urls")),
    # Root URL → anonymous home page
    path("", lambda request: redirect("shopcore:anonymous_home"), name="root_redirect"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
