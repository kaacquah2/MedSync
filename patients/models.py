"""
Central Patient Registry.

Every patient has a unique National Health ID (NHID-XXXXXXXX) that is the
single key used across all participating hospitals. All PII/PHI is stored
in encrypted fields (Fernet AES) — the primary database rows contain ciphertext.

Blind-index columns (national_id_hash, name_hash) are HMAC-SHA256 hashes
of the normalised plaintext, keyed with BLIND_INDEX_KEY. They allow exact-
match searches on encrypted columns without storing plaintext.

Partial name searches utilize substring trigrams in PatientSearchToken.
Note: Trigram tokens represent low-entropy HMAC hashes (~17,576 Latin trigrams keyspace).
Deployments must maintain strict isolation of BLIND_INDEX_KEY to protect against
precomputed dictionary attacks and frequency analysis on partial search tokens.
See known_limitations.md §1 for full risk posture and mitigations.
"""

import logging
import re
import uuid
from datetime import date, datetime

from django.core.exceptions import ValidationError
from django.db import models

from core.blind_index import make_blind_index
from core.fields import EncryptedCharField, EncryptedTextField
from core.models import TimeStampedModel

logger = logging.getLogger(__name__)


def validate_date_of_birth(value: str):
    """
    Validate that date_of_birth is a valid calendar date in YYYY-MM-DD format
    and is not in the future.
    """
    if not value:
        return
    val_str = str(value).strip()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", val_str):
        raise ValidationError("Date of birth must be in YYYY-MM-DD format.")
    try:
        dt = datetime.strptime(val_str, "%Y-%m-%d").date()
    except ValueError as e:
        raise ValidationError("Invalid calendar date for date of birth.") from e
    if dt > date.today():
        raise ValidationError("Date of birth cannot be in the future.")


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
        validators=[validate_date_of_birth],
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

    def clean(self):
        super().clean()
        if self.date_of_birth:
            validate_date_of_birth(self.date_of_birth)

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
        except Exception as exc:
            logger.warning(
                "Failed to compute name blind index for patient %s: %s",
                self.universal_id,
                exc,
            )
            self.name_hash = ""

        try:
            nid = str(self.national_id or "")
            self.national_id_hash = make_blind_index(nid) if nid else ""
        except Exception as exc:
            logger.warning(
                "Failed to compute national_id blind index for patient %s: %s",
                self.universal_id,
                exc,
            )
            self.national_id_hash = ""

        super().save(*args, **kwargs)

        try:
            tokens = generate_name_trigrams(self.first_name, self.last_name)
            existing_tokens = set(self.search_tokens.values_list("token_hash", flat=True))
            new_hashes = {make_blind_index(tok) for tok in tokens if tok}

            to_delete = existing_tokens - new_hashes
            if to_delete:
                self.search_tokens.filter(token_hash__in=to_delete).delete()

            to_add = new_hashes - existing_tokens
            if to_add:
                PatientSearchToken.objects.bulk_create(
                    [PatientSearchToken(patient=self, token_hash=h) for h in to_add]
                )
        except Exception as exc:
            logger.exception(
                "Failed to synchronize PatientSearchTokens for patient %s (pk=%s): %s",
                self.universal_id,
                self.pk,
                exc,
            )
            raise

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


class PatientSearchToken(models.Model):
    """
    Stores HMAC-SHA256 blind indexed trigrams of patient names.
    Enables secure, indexed partial name lookups without sequential O(N) table scans.
    """

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="search_tokens")
    token_hash = models.CharField(max_length=64, db_index=True)

    class Meta:
        unique_together = ("patient", "token_hash")
        verbose_name = "Patient Search Token"
        verbose_name_plural = "Patient Search Tokens"

    def __str__(self):
        return f"SearchToken(Patient={self.patient.universal_id}, Hash={self.token_hash[:12]}…)"


def generate_name_trigrams(first_name: str, last_name: str) -> set[str]:
    """Generate the set of name trigrams (and short words) for search indexing."""
    fn = str(first_name or "").strip().lower()
    ln = str(last_name or "").strip().lower()
    full = f"{fn} {ln}".strip()
    words = [w for w in full.split() if w]
    tokens = set()
    for word in words:
        if len(word) < 3:
            tokens.add(word)
        else:
            for i in range(len(word) - 2):
                tokens.add(word[i : i + 3])
    return tokens
