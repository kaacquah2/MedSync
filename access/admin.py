"""Admin registrations for the access control app."""

from django.contrib import admin

from .models import BreakGlassAccess, PatientConsent, TreatmentRelationship


@admin.register(TreatmentRelationship)
class TreatmentRelationshipAdmin(admin.ModelAdmin):
    list_display = ["clinician", "patient", "hospital", "started_at", "ended_at"]
    list_filter = ["hospital"]
    search_fields = ["clinician__username", "patient__universal_id"]
    readonly_fields = ["started_at"]
    ordering = ["-started_at"]

    def has_delete_permission(self, request, obj=None):
        # Only SYSTEM_ADMIN can close relationships (via the close() method)
        return request.user.role == "SYSTEM_ADMIN"


@admin.register(BreakGlassAccess)
class BreakGlassAccessAdmin(admin.ModelAdmin):
    list_display = ["actor", "patient", "created_at", "expires_at", "mfa_reverified"]
    list_filter = ["mfa_reverified"]
    search_fields = ["actor__username", "patient__universal_id"]
    readonly_fields = ["actor", "patient", "reason", "created_at", "expires_at", "mfa_reverified"]
    ordering = ["-created_at"]

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PatientConsent)
class PatientConsentAdmin(admin.ModelAdmin):
    list_display = ["patient", "hospital", "granted", "granted_at"]
    list_filter = ["granted", "hospital"]
    search_fields = ["patient__universal_id"]
    ordering = ["-granted_at"]
