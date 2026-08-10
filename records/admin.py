from django.contrib import admin

from .models import Diagnosis, Encounter, LabResult, Prescription


class DiagnosisInline(admin.TabularInline):
    model = Diagnosis
    extra = 0
    readonly_fields = ["created_by", "created_at"]


class PrescriptionInline(admin.TabularInline):
    model = Prescription
    extra = 0
    readonly_fields = ["created_by", "created_at"]


class LabResultInline(admin.TabularInline):
    model = LabResult
    extra = 0
    readonly_fields = ["created_by", "created_at"]


@admin.register(Encounter)
class EncounterAdmin(admin.ModelAdmin):
    list_display = ["patient", "encounter_type", "created_at_hospital", "created_by", "created_at"]
    list_filter = ["encounter_type", "created_at_hospital"]
    search_fields = ["patient__universal_id"]
    readonly_fields = ["created_by", "created_at_hospital", "created_at", "updated_at"]
    inlines = [DiagnosisInline, PrescriptionInline, LabResultInline]
