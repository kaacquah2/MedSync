"""
Central Patient Registry.

Every patient has a unique National Health ID (NHID-XXXXXXXX) that is the
single key used across all participating hospitals.  All PII/PHI is stored
in encrypted fields (Fernet AES) — the database rows contain ciphertext.

Blind-index columns (national_id_hash, name_hash) are HMAC-SHA256 hashes
of the normalised plaintext, keyed with BLIND_INDEX_KEY.  They allow exact-
match searches on encrypted columns without storing or exposing plaintext.
"""

import uuid

from django.db import models

from core.blind_index import make_blind_index
from core.fields import EncryptedCharField, EncryptedTextField
from core.models import TimeStampedModel


def generate_nhid():
    """Generate a unique 8-character hex National Health ID."""
    return f"NHID-{uuid.uuid4().hex[:8].upper()}"


class Patient(TimeStampedModel):
    """Central patient record — shared across all hospitals."""

    class BloodGroup(models.TextChoices):
        A_POS = "A+", "A+"
        A_NEG = "A-", "A-"
        B_POS = "B+", "B+"
        B_NEG = "B-", "B-"
        AB_POS = "AB+", "AB+"
        AB_NEG = "AB-", "AB-"
        O_POS = "O+", "O+"
        O_NEG = "O-", "O-"
        UNKNOWN = "?", "Unknown"

    class Sex(models.TextChoices):
        MALE = "M", "Male"
        FEMALE = "F", "Female"
        OTHER = "O", "Other / Prefer not to say"

    # ── Universal identifier ──────────────────────────────────────────────
    universal_id = models.CharField(
        max_length=20,
        unique=True,
        default=generate_nhid,
        editable=False,
        db_index=True,
        verbose_name="National Health ID",
    )

    # ── Encrypted PII / demographics ─────────────────────────────────────
    # Stored as Fernet ciphertext — the DB contains NO plaintext.
    first_name = EncryptedCharField(max_length=100, verbose_name="First name")
    last_name = EncryptedCharField(max_length=100, verbose_name="Last name / Surname")
    date_of_birth = EncryptedCharField(
        max_length=20,
        verbose_name="Date of birth",
        help_text="YYYY-MM-DD",
    )
    national_id = EncryptedCharField(
        max_length=50,
        blank=True,
        verbose_name="National ID / Passport",
    )
    phone = EncryptedCharField(max_length=20, blank=True)
    email = EncryptedCharField(max_length=254, blank=True)
    address = EncryptedTextField(blank=True)

    # ── Blind-index columns (HMAC-SHA256 of normalised plaintext) ─────────
    # These allow exact-match searches without exposing plaintext in the DB.
    # Automatically updated by save().
    name_hash = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        editable=False,
        help_text="HMAC-SHA256 blind index of 'first_name last_name' (lowercase). "
        "Used for exact name lookups without decrypting all rows.",
    )
    national_id_hash = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        editable=False,
        help_text="HMAC-SHA256 blind index of national_id. "
        "Used for exact national-ID lookups without decrypting all rows.",
    )

    # ── Non-sensitive clinical constants ─────────────────────────────────
    sex = models.CharField(max_length=1, choices=Sex.choices, default=Sex.OTHER)
    blood_group = models.CharField(
        max_length=3,
        choices=BloodGroup.choices,
        default=BloodGroup.UNKNOWN,
    )

    # ── Registering hospital ──────────────────────────────────────────────
    # This field is the "same-hospital" authorization signal used by
    # access.permissions.can_access_patient(): a clinician whose hospital FK
    # matches this field is granted access without a TreatmentRelationship or
    # BreakGlassAccess grant.  Do NOT remove or repurpose this field without
    # updating the access gate in access/permissions.py.
    registered_at_hospital = models.ForeignKey(
        "hospitals.Hospital",
        on_delete=models.SET_NULL,
        null=True,
        related_name="registered_patients",
        verbose_name="Registering hospital",
    )
    registered_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="registered_patients",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Patient"
        verbose_name_plural = "Patients"

    def save(self, *args, **kwargs):
        """Auto-compute blind indexes before every save."""
        # first_name / last_name may arrive as plaintext (before encryption)
        # or as already-decrypted values via from_db_value — both are fine here
        # because make_blind_index normalises to lowercase and the Fernet ciphertext
        # will never match a HMAC of the plaintext.
        try:
            fn = str(self.first_name or "")
            ln = str(self.last_name or "")
            full = f"{fn} {ln}".strip()
            self.name_hash = make_blind_index(full) if full else ""
        except Exception:
            self.name_hash = ""

        try:
            nid = str(self.national_id or "")
            self.national_id_hash = make_blind_index(nid) if nid else ""
        except Exception:
            self.national_id_hash = ""

        super().save(*args, **kwargs)

    def __str__(self):
        # Encrypted fields decrypt transparently on attribute access
        return f"{self.first_name} {self.last_name} ({self.universal_id})"

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}"


class PatientAlert(TimeStampedModel):
    """
    A patient allergy or clinical alert — visible to every clinician who
    accesses this patient's record, regardless of their home hospital.

    This is the cross-hospital safety information feature: an allergy
    recorded at UGMC is automatically visible to a KATH clinician opening
    the same patient, demonstrating the value of the shared central record.
    """

    class Kind(models.TextChoices):
        ALLERGY = "ALLERGY", "Allergy"
        ALERT = "ALERT", "Clinical Alert"

    class Severity(models.TextChoices):
        MILD = "MILD", "Mild"
        MODERATE = "MODERATE", "Moderate"
        SEVERE = "SEVERE", "Severe"
        LIFE_THREAT = "LIFE_THREAT", "Life-threatening"

    patient = models.ForeignKey(
        Patient,
        on_delete=models.CASCADE,
        related_name="alerts",
    )
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.ALLERGY)
    label = EncryptedCharField(
        max_length=200,
        verbose_name="Substance / description",
        help_text="E.g. Penicillin, Latex, Contrast dye, Peanuts.",
    )
    severity = models.CharField(
        max_length=15,
        choices=Severity.choices,
        default=Severity.MODERATE,
    )
    reaction = EncryptedTextField(
        blank=True,
        verbose_name="Reaction notes",
        help_text="Describe the observed reaction (optional).",
    )
    recorded_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="recorded_alerts",
    )
    recorded_at_hospital = models.ForeignKey(
        "hospitals.Hospital",
        on_delete=models.SET_NULL,
        null=True,
        related_name="recorded_alerts",
        help_text="Hospital where this alert was first recorded. "
        "Shown to clinicians from other hospitals to make provenance clear.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Set to False to deactivate (do not delete — preserve audit history).",
    )

    class Meta:
        # Highest severity first, then newest
        ordering = ["-is_active", "-severity", "-created_at"]
        verbose_name = "Patient Alert / Allergy"
        verbose_name_plural = "Patient Alerts / Allergies"

    def __str__(self):
        return f"{self.get_kind_display()}: {self.label} ({self.get_severity_display()}) — {self.patient}"

    @property
    def is_high_risk(self) -> bool:
        """True for severe or life-threatening alerts — shown in red."""
        return self.severity in (self.Severity.SEVERE, self.Severity.LIFE_THREAT)
