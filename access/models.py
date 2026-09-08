"""
Inter-hospital access control models.

Three mechanisms grant a clinician cross-hospital patient access:
  1. TreatmentRelationship — an explicit, audited care relationship.
     Auto-created when a clinician opens an encounter for a patient.
  2. BreakGlassAccess — an emergency, reason-required, time-boxed override.
     Requires re-MFA when MFA_ENFORCED=True; always logged and reviewed.
  3. PatientConsent — the patient's own consent record (prototype layer;
     not currently enforced as a hard gate, but expressed in the data model).

The central decision function is access.permissions.can_access_patient().
"""

from datetime import timedelta

from django.db import models
from django.utils import timezone

from core.fields import EncryptedTextField

# Break-glass grants expire after this many hours
BREAK_GLASS_DURATION_HOURS = 1


# ── TreatmentRelationship ──────────────────────────────────────────────────


class TreatmentRelationshipManager(models.Manager):
    def active_for(self, user, patient):
        """Return queryset of active (non-expired) relationships for user+patient."""
        now = timezone.now()
        return self.filter(
            clinician=user,
            patient=patient,
            started_at__lte=now,
        ).filter(models.Q(ended_at__isnull=True) | models.Q(ended_at__gt=now))


class TreatmentRelationship(models.Model):
    """
    Records an active clinical care relationship between a clinician and patient.

    Grants the clinician cross-hospital access to the patient's records.
    Auto-created when a clinician opens an encounter for a patient they do not
    already have a relationship with.
    """

    clinician = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="treatment_relationships",
    )
    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.CASCADE,
        related_name="treatment_relationships",
    )
    hospital = models.ForeignKey(
        "hospitals.Hospital",
        on_delete=models.SET_NULL,
        null=True,
        related_name="treatment_relationships",
        help_text="Hospital where this care relationship was established.",
    )
    started_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Null = relationship is still active.",
    )
    reason = EncryptedTextField(
        blank=True,
        help_text="Clinical reason for the treatment relationship.",
    )

    objects = TreatmentRelationshipManager()

    class Meta:
        ordering = ["-started_at"]
        verbose_name = "Treatment Relationship"
        verbose_name_plural = "Treatment Relationships"
        indexes = [
            models.Index(fields=["clinician", "patient"]),
        ]

    def __str__(self):
        return f"{self.clinician.username} → {self.patient.universal_id}"

    def close(self):
        """Mark this relationship as ended now."""
        self.ended_at = timezone.now()
        self.save(update_fields=["ended_at"])


# ── BreakGlassAccess ───────────────────────────────────────────────────────


class BreakGlassAccessManager(models.Manager):
    def active_for(self, user, patient):
        """Return queryset of non-expired break-glass grants for user+patient."""
        return self.filter(
            actor=user,
            patient=patient,
            expires_at__gt=timezone.now(),
        )


class BreakGlassAccess(models.Model):
    """
    Emergency override granting a clinician temporary, time-boxed access to a
    patient's records without an active treatment relationship.

    - Requires an explicit non-blank reason (enforced at the form layer).
    - Time-boxed to BREAK_GLASS_DURATION_HOURS hours from creation.
    - Audited immediately on creation (BREAK_GLASS action in AuditLog).
    - mfa_reverified records whether the clinician re-entered their TOTP code.
    """

    actor = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="break_glass_accesses",
    )
    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.PROTECT,
        related_name="break_glass_accesses",
    )
    reason = EncryptedTextField(
        help_text="Required: clinical justification for this emergency override.",
    )
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    mfa_reverified = models.BooleanField(
        default=False,
        help_text="True if the clinician re-verified their TOTP code at override time.",
    )

    objects = BreakGlassAccessManager()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Break-Glass Access"
        verbose_name_plural = "Break-Glass Accesses"
        indexes = [
            models.Index(fields=["actor", "patient", "expires_at"]),
        ]

    def save(self, *args, **kwargs):
        # Auto-compute expiry on first save if not provided
        if not self.pk and not self.expires_at:
            self.expires_at = self.created_at + timedelta(hours=BREAK_GLASS_DURATION_HOURS)
        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"BREAK-GLASS: {self.actor.username} → {self.patient.universal_id}"
            f" (expires {self.expires_at:%Y-%m-%d %H:%M})"
        )

    @property
    def is_active(self):
        return timezone.now() < self.expires_at


# ── PatientConsent ─────────────────────────────────────────────────────────


class PatientConsent(models.Model):
    """
    Records a patient's consent for a specific hospital to access their records.

    In this prototype, TreatmentRelationship / BreakGlassAccess are the
    primary enforcement mechanism; this model expresses patient preferences
    for future FHIR/consent-based sharing workflows.
    """

    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.CASCADE,
        related_name="consents",
    )
    hospital = models.ForeignKey(
        "hospitals.Hospital",
        on_delete=models.CASCADE,
        related_name="patient_consents",
    )
    granted = models.BooleanField(default=True)
    granted_at = models.DateTimeField(default=timezone.now)
    revoked_at = models.DateTimeField(null=True, blank=True)
    notes = EncryptedTextField(blank=True)

    class Meta:
        unique_together = [("patient", "hospital")]
        ordering = ["-granted_at"]
        verbose_name = "Patient Consent"
        verbose_name_plural = "Patient Consents"

    def __str__(self):
        status = "Granted" if self.granted else "Revoked"
        return f"{status}: {self.patient.universal_id} → {self.hospital}"
