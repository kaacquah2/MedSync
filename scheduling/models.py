"""Scheduling app — Appointments."""

from django.db import models

from core.fields import EncryptedTextField
from core.models import TimeStampedModel


class Appointment(TimeStampedModel):
    """A scheduled patient appointment with a provider at a hospital."""

    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        CHECKED_IN = "checked_in", "Checked In"
        IN_PROGRESS = "in_progress", "In Progress"
        COMPLETED = "completed", "Completed"
        NO_SHOW = "no_show", "No Show"
        CANCELLED = "cancelled", "Cancelled"

    class AppointmentType(models.TextChoices):
        OUTPATIENT = "outpatient", "Outpatient Consultation"
        FOLLOW_UP = "follow_up", "Follow-Up"
        PROCEDURE = "procedure", "Procedure / Intervention"
        LAB = "lab", "Laboratory Visit"
        EMERGENCY = "emergency", "Emergency"

    patient = models.ForeignKey(
        "patients.Patient", on_delete=models.PROTECT, related_name="appointments"
    )
    provider = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="appointments_as_provider",
        help_text="The doctor or nurse the patient is seeing.",
    )
    hospital = models.ForeignKey(
        "hospitals.Hospital", on_delete=models.CASCADE, related_name="appointments"
    )
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="appointments_created",
    )
    scheduled_for = models.DateTimeField()
    duration_minutes = models.PositiveSmallIntegerField(default=30)
    appointment_type = models.CharField(
        max_length=15, choices=AppointmentType.choices, default=AppointmentType.OUTPATIENT
    )
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.SCHEDULED)
    reason = EncryptedTextField(blank=True, verbose_name="Reason for visit")
    notes = EncryptedTextField(blank=True, verbose_name="Administrative notes")

    class Meta:
        ordering = ["scheduled_for"]
        verbose_name = "Appointment"

    def __str__(self):
        provider_name = self.provider.get_full_name() if self.provider else "Unassigned"
        return (
            f"{self.patient.universal_id} → {provider_name} "
            f"@ {self.scheduled_for.strftime('%Y-%m-%d %H:%M')}"
        )
