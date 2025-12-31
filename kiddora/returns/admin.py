from django.contrib import admin
from .models import Return


@admin.register(Return)
class ReturnAdmin(admin.ModelAdmin):
    list_display = ("order", "product", "status", "created_at")
    list_filter = ("status",)
