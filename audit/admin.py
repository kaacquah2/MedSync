from django.contrib import admin

from .models import AuditLog, AuditLogReview


@admin.register(AuditLogReview)
class AuditLogReviewAdmin(admin.ModelAdmin):
    list_display = ["audit_log", "reviewed_by", "reviewed_at"]
    list_filter = ["reviewed_by", "reviewed_at"]
    search_fields = ["audit_log__id", "reviewed_by__username"]


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = [
        "timestamp",
        "actor_username",
        "actor_role",
        "actor_hospital",
        "action",
        "patient_nhid",
        "is_cross_hospital",
        "ip_address",
    ]
    list_filter = ["action", "is_cross_hospital", "actor_role"]
    search_fields = ["actor_username", "patient_nhid", "ip_address"]
    readonly_fields = [
        f.name
        for f in AuditLog._meta.get_fields()
        if hasattr(f, "name") and not f.many_to_many and not f.one_to_many
    ]
    ordering = ["-timestamp"]

    def has_add_permission(self, request):
        return False  # No manual creation of audit entries

    def has_change_permission(self, request, obj=None):
        return False  # No editing

    def has_delete_permission(self, request, obj=None):
        return False  # No deletion
