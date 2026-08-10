from django.contrib import admin

from .models import Patient


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ["universal_id", "sex", "blood_group", "registered_at_hospital", "created_at"]
    list_filter = ["sex", "blood_group", "registered_at_hospital"]
    search_fields = ["universal_id"]
    readonly_fields = ["universal_id", "created_at", "updated_at", "registered_by"]
    ordering = ["-created_at"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("registered_at_hospital")
