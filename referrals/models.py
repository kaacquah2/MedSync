"""Referrals app — inter-hospital and intra-hospital patient referrals."""

from django.db import models

from core.fields import EncryptedTextField
from core.models import TimeStampedModel


class Referral(TimeStampedModel):
    """A clinical referral — from one provider/hospital to another."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SENT = "sent", "Sent"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    class Priority(models.TextChoices):
        ROUTINE = "routine", "Routine"
        URGENT = "urgent", "Urgent"
        STAT = "stat", "STAT (Emergency)"

    patient = models.ForeignKey(
        "patients.Patient", on_delete=models.PROTECT, related_name="referrals"
    )
    from_hospital = models.ForeignKey(
        "hospitals.Hospital",
        on_delete=models.PROTECT,
        related_name="outgoing_referrals",
    )
    to_hospital = models.ForeignKey(
        "hospitals.Hospital",
        on_delete=models.PROTECT,
        related_name="incoming_referrals",
    )
    from_provider = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="referrals_sent",
    )
    to_provider = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="referrals_received",
        help_text="Specific receiving doctor if known; otherwise any clinician at the to_hospital.",
    )
    reason = EncryptedTextField(verbose_name="Reason / clinical summary")
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.ROUTINE)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    status_notes = EncryptedTextField(
        blank=True,
        verbose_name="Status notes",
        help_text="Reason for rejection, acceptance notes, etc.",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Referral"

    def __str__(self):
        return (
            f"Referral {self.pk}: {self.patient.universal_id} "
            f"{self.from_hospital.code} → {self.to_hospital.code} "
            f"({self.get_status_display()})"
        )
