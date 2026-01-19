from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, UserAddress


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = (
        "id",
        "email",
        "username",
        "role",
        "is_active",
        "is_staff",
        "email_verified",
        "created_at",
    )

    list_filter = (
        "role",
        "is_active",
        "is_staff",
        "email_verified",
    )

    search_fields = (
        "email",
        "username",
        "phone",
        "full_name",
    )

    ordering = ("-created_at",)

    fieldsets = (
        ("Authentication", {
            "fields": (
                "email",
                "username",
                "password",
            )
        }),
        ("Personal Info", {
            "fields": (
                "first_name",
                "last_name",
                "full_name",
                "phone",
                "profile_image",
            )
        }),
        ("Role & Status", {
            "fields": (
                "role",
                "email_verified",
                "is_active",
                "is_staff",
                "is_superuser",
            )
        }),
        ("OTP Details", {
            "fields": (
                "otp",
                "otp_created_at",
            )
        }),
        ("Important Dates", {
            "fields": (
                "last_login",
                "date_joined",
                "created_at",
                "updated_at",
            )
        }),
    )

    readonly_fields = (
        "created_at",
        "updated_at",
        "last_login",
        "date_joined",
    )

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": (
                "email",
                "username",
                "password1",
                "password2",
                "role",
                "is_active",
                "is_staff",
            ),
        }),
    )


@admin.register(UserAddress)
class UserAddressAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "city",
        "state",
        "country",
        "pincode",
        "address_type",
        "is_default",
        "created_at",
    )

    list_filter = (
        "address_type",
        "is_default",
        "country",
    )

    search_fields = (
        "user__email",
        "city",
        "state",
        "pincode",
    )
