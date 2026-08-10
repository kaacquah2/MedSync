"""Shifts app — nurse shift records and handover notes."""

from django.db import models
from django.utils import timezone

from core.fields import EncryptedTextField
from core.models import TimeStampedModel


class ShiftRecord(TimeStampedModel):
    """Records a nurse's shift — start, end, and break time."""

    user = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="shift_records"
    )
    ward = models.ForeignKey(
        "hospitals.Ward",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shifts",
    )
    started_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)
    break_minutes = models.PositiveSmallIntegerField(
        default=0, help_text="Total break time in minutes"
    )

    class Meta:
        ordering = ["-started_at"]
        verbose_name = "Shift Record"

    def __str__(self):
        return (
            f"{self.user.get_full_name()} — "
            f"{self.started_at.strftime('%Y-%m-%d %H:%M')} "
            f"{'(active)' if not self.ended_at else '→ ' + self.ended_at.strftime('%H:%M')}"
        )

    @property
    def is_active(self):
        return self.ended_at is None


class Handover(TimeStampedModel):
    """
    Clinical shift handover note — passed from one nurse to the next.
    Summary is encrypted as it may contain clinical detail.
    """

    shift = models.ForeignKey(
        ShiftRecord, on_delete=models.CASCADE, related_name="handovers", null=True, blank=True
    )
    from_user = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="handovers_given"
    )
    to_user = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="handovers_received",
    )
    ward = models.ForeignKey(
        "hospitals.Ward",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="handovers",
    )
    summary = EncryptedTextField(verbose_name="Handover summary")
    acknowledged_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="handovers_acknowledged",
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Handover"

    def __str__(self):
        to_name = self.to_user.get_full_name() if self.to_user else "Unknown"
        return (
            f"Handover from {self.from_user.get_full_name()} to {to_name} "
            f"@ {self.created_at.strftime('%Y-%m-%d %H:%M')}"
        )
