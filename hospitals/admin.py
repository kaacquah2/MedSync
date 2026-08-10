from django.contrib import admin

from .models import Hospital


@admin.register(Hospital)
class HospitalAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "city", "country", "is_active", "created_at"]
    list_filter = ["is_active", "country"]
    search_fields = ["name", "code", "city"]
    ordering = ["name"]
