from django.contrib import admin
from .models import CustomUser, UserAddress

@admin.register(CustomUser)
class CustomUserAdmin(admin.ModelAdmin):
    list_display = (
        "id", "email","full_name", "role",
        "is_active", "email_verified", "date_joined"
    )
    list_filter = ("role", "is_active", "email_verified")
    search_fields = ("email", "phone","full_name")
    ordering = ("-date_joined",)
    readonly_fields = ("last_login", "date_joined", "created_at", "updated_at")
    actions = ["block_users", "unblock_users"]
    def block_users(self, request, queryset):
        queryset.update(is_active=False)
    def unblock_users(self, request, queryset):
        queryset.update(is_active=True)

@admin.register(UserAddress)
class UserAddressAdmin(admin.ModelAdmin):
    list_display = ("user", "city", "state", "country", "is_default")
    list_filter = ("country", "state")
    search_fields = ("user__email", "city", "pincode")

