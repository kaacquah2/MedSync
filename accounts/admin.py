from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ["username", "get_full_name", "role", "hospital", "is_active"]
    list_filter = ["role", "hospital", "is_active"]
    search_fields = ["username", "first_name", "last_name", "email"]
    ordering = ["username"]

    fieldsets = UserAdmin.fieldsets + (
        ("EMR Role & Hospital", {"fields": ("role", "hospital", "phone", "bio")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("EMR Role & Hospital", {"fields": ("role", "hospital", "phone")}),
    )
