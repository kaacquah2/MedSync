"""
Clinical Records models.

Structure:
  Patient ─► VitalSign       (numeric vitals — unencrypted for charting queries)
  Patient ─► LabOrder        (order workflow — test_name unencrypted for worklist filtering)
  Patient ─► Encounter ─► Diagnosis  (encrypted notes)
                        ─► Prescription (encrypted details)
                        ─► LabResult    (encrypted findings, including test_name)

Design note — intentional plaintext fields:
  VitalSign fields are unencrypted to enable aggregate SQL queries (charting, trends).
  Operational metadata (e.g. priority, status) remains plaintext, while all diagnostic
  codes (ICD-10, SNOMED CT), medication codes (RxNorm), lab order test names, and LOINC
  codes are encrypted with EncryptedCharField to comply with Ghana Data Protection Act 2012
  (Act 843 Part V §32) and HIPAA § 164.514. Exact-match searches are supported via keyed
  HMAC-SHA256 blind index hash columns without exposing clinical taxonomy in plaintext.

Each record is stamped with:
  - created_by          : the clinician who created it
  - created_at_hospital : the hospital where the encounter occurred

This stamp is what enables the audit layer to detect cross-hospital access
(actor.hospital ≠ created_at_hospital on a subsequent access).
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from core.blind_index import make_blind_index
from core.fields import EncryptedCharField, EncryptedTextField
from core.models import TimeStampedModel
from records.validators import (
    validate_icd10,
    validate_loinc,
    validate_rxnorm,
    validate_snomed,
)


class ConfidentialityLevel(models.TextChoices):
    NORMAL = "normal", "Normal (Standard Clinical Record)"
    RESTRICTED = "restricted", "Restricted (Mental Health, HIV, Sensitive Care)"
    VERY_RESTRICTED = "very_restricted", "Very Restricted (VIP / Special Category)"


class Encounter(TimeStampedModel):
    """A clinical visit / contact between a patient and a facility."""

    ConfidentialityLevel = ConfidentialityLevel

    class EncounterType(models.TextChoices):
        OUTPATIENT = "OPD", "Outpatient (OPD)"
        INPATIENT = "IPD", "Inpatient (IPD)"
        EMERGENCY = "EMRG", "Emergency"
        FOLLOW_UP = "FU", "Follow-up"
        TELEMEDICINE = "TM", "Telemedicine"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        IN_PROGRESS = "in_progress", "In Progress"
        COMPLETED = "completed", "Completed"
        SIGNED_OFF = "signed_off", "Signed Off"

    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.PROTECT,
        related_name="encounters",
    )
    encounter_type = models.CharField(
        max_length=4,
        choices=EncounterType.choices,
        default=EncounterType.OUTPATIENT,
    )
    status = models.CharField(
        max_length=15,
        choices=Status.choices,
        default=Status.OPEN,
        db_index=True,
        help_text="Lifecycle state of the encounter. Open → In Progress → Completed → Signed Off.",
    )
    chief_complaint = EncryptedTextField(
        verbose_name="Chief complaint / presenting problem",
    )
    notes = EncryptedTextField(blank=True, verbose_name="Clinical notes")
    confidentiality = models.CharField(
        max_length=20,
        choices=ConfidentialityLevel.choices,
        default=ConfidentialityLevel.NORMAL,
        db_index=True,
        help_text="Data sensitivity tier under Act 843 §37 / ISO 22600.",
    )

    # Who and where
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="encounters_created",
    )
    created_at_hospital = models.ForeignKey(
        "hospitals.Hospital",
        on_delete=models.SET_NULL,
        null=True,
        related_name="encounters",
        verbose_name="Hospital (encounter location)",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Encounter"
        indexes = [
            models.Index(fields=["status", "created_at"], name="encounter_status_created_idx"),
        ]

    def __str__(self):
        return f"{self.get_encounter_type_display()} — {self.patient.universal_id} @ {self.created_at.date()}"


class Diagnosis(TimeStampedModel):
    """A diagnosis attached to an encounter."""

    encounter = models.ForeignKey(Encounter, on_delete=models.PROTECT, related_name="diagnoses")
    icd_code = EncryptedCharField(
        max_length=20,
        blank=True,
        validators=[validate_icd10],
        verbose_name="ICD-10 code",
        help_text="ICD-10-CM code, e.g. J18.9 (Pneumonia, unspecified).",
    )
    icd_code_hash = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        editable=False,
        help_text="HMAC-SHA256 blind index of icd_code for exact-match querying.",
    )
    snomed_code = EncryptedCharField(
        max_length=20,
        blank=True,
        validators=[validate_snomed],
        verbose_name="SNOMED CT code",
        help_text="Optional SNOMED CT concept ID for interoperability.",
    )
    snomed_code_hash = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        editable=False,
        help_text="HMAC-SHA256 blind index of snomed_code for exact-match querying.",
    )
    description = EncryptedTextField(verbose_name="Diagnosis description")
    is_primary = models.BooleanField(default=True)
    confidentiality = models.CharField(
        max_length=20,
        choices=ConfidentialityLevel.choices,
        default=ConfidentialityLevel.NORMAL,
        db_index=True,
        help_text="Data sensitivity tier under Act 843 §37 / ISO 22600.",
    )
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="diagnoses_created",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Diagnosis"
        verbose_name_plural = "Diagnoses"

    def save(self, *args, **kwargs):
        try:
            code = str(self.icd_code or "").strip()
            self.icd_code_hash = make_blind_index(code) if code else ""
        except Exception:
            self.icd_code_hash = ""
        try:
            snomed = str(self.snomed_code or "").strip()
            self.snomed_code_hash = make_blind_index(snomed) if snomed else ""
        except Exception:
            self.snomed_code_hash = ""

        if "update_fields" in kwargs and kwargs["update_fields"] is not None:
            uf = set(kwargs["update_fields"])
            if "icd_code" in uf:
                uf.add("icd_code_hash")
            if "snomed_code" in uf:
                uf.add("snomed_code_hash")
            kwargs["update_fields"] = uf

        super().save(*args, **kwargs)

    def __str__(self):
        desc = self.description or ""
        prefix = f"{self.icd_code}: " if self.icd_code else ""
        return f"{prefix}{desc[:40]}…" if len(desc) > 40 else f"{prefix}{desc}"


class Prescription(TimeStampedModel):
    """A medication prescription linked to an encounter."""

    class PrescriptionStatus(models.TextChoices):
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        DISCONTINUED = "discontinued", "Discontinued"

    encounter = models.ForeignKey(Encounter, on_delete=models.PROTECT, related_name="prescriptions")
    drug_name = EncryptedCharField(max_length=200, verbose_name="Drug / Medication name")
    rxnorm_code = EncryptedCharField(
        max_length=20,
        blank=True,
        validators=[validate_rxnorm],
        verbose_name="RxNorm code",
        help_text="Optional RxNorm CUI for structured medication interoperability.",
    )
    rxnorm_code_hash = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        editable=False,
        help_text="HMAC-SHA256 blind index of rxnorm_code for exact-match querying.",
    )
    dosage = EncryptedCharField(max_length=100, verbose_name="Dosage & route")
    frequency = EncryptedCharField(max_length=100, verbose_name="Frequency / duration")
    instructions = EncryptedTextField(blank=True, verbose_name="Additional instructions")
    status = models.CharField(
        max_length=15,
        choices=PrescriptionStatus.choices,
        default=PrescriptionStatus.ACTIVE,
        db_index=True,
        help_text="Lifecycle state: active, completed, or discontinued.",
    )
    discontinued_reason = EncryptedTextField(
        blank=True,
        verbose_name="Discontinuation reason",
        help_text="Required when status is set to discontinued.",
    )
    allergy_override_reason = EncryptedTextField(
        blank=True,
        verbose_name="Allergy override reason",
        help_text="Clinical justification if prescribed despite an active allergy conflict.",
    )
    valid_until = models.DateField(
        null=True,
        blank=True,
        verbose_name="Valid until (date)",
        help_text="Optional expiry date after which this prescription should not be filled.",
    )
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="prescriptions_created",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Prescription"
        indexes = [
            models.Index(fields=["status", "created_at"], name="rx_status_created_idx"),
        ]

    def save(self, *args, **kwargs):
        try:
            rx = str(self.rxnorm_code or "").strip()
            self.rxnorm_code_hash = make_blind_index(rx) if rx else ""
        except Exception:
            self.rxnorm_code_hash = ""

        if "update_fields" in kwargs and kwargs["update_fields"] is not None:
            uf = set(kwargs["update_fields"])
            if "rxnorm_code" in uf:
                uf.add("rxnorm_code_hash")
            kwargs["update_fields"] = uf

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.drug_name} — {self.dosage}"


class LabOrder(TimeStampedModel):
    """A laboratory test order — workflow precursor to LabResult."""

    class Priority(models.TextChoices):
        ROUTINE = "routine", "Routine"
        URGENT = "urgent", "Urgent"
        STAT = "stat", "STAT (Immediate)"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        IN_PROGRESS = "in_progress", "In Progress"
        RESULTED = "resulted", "Resulted"
        CANCELLED = "cancelled", "Cancelled"

    encounter = models.ForeignKey(
        Encounter, on_delete=models.PROTECT, related_name="lab_orders", null=True, blank=True
    )
    patient = models.ForeignKey(
        "patients.Patient", on_delete=models.PROTECT, related_name="lab_orders"
    )
    ordered_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, related_name="lab_orders_created"
    )
    test_name = EncryptedCharField(max_length=200, verbose_name="Test name")
    test_name_hash = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        editable=False,
        help_text="HMAC-SHA256 blind index of test_name for exact-match querying.",
    )
    loinc_code = EncryptedCharField(
        max_length=20,
        blank=True,
        validators=[validate_loinc],
        verbose_name="LOINC code",
        help_text="Optional LOINC code for structured lab interoperability.",
    )
    loinc_code_hash = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        editable=False,
        help_text="HMAC-SHA256 blind index of loinc_code for exact-match querying.",
    )
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.ROUTINE)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.PENDING)
    clinical_notes = EncryptedTextField(blank=True, verbose_name="Clinical notes for lab")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Lab Order"
        indexes = [
            models.Index(fields=["status", "created_at"], name="laborder_status_created_idx"),
        ]

    def save(self, *args, **kwargs):
        try:
            tn = str(self.test_name or "").strip()
            self.test_name_hash = make_blind_index(tn) if tn else ""
        except Exception:
            self.test_name_hash = ""
        try:
            lc = str(self.loinc_code or "").strip()
            self.loinc_code_hash = make_blind_index(lc) if lc else ""
        except Exception:
            self.loinc_code_hash = ""

        if "update_fields" in kwargs and kwargs["update_fields"] is not None:
            uf = set(kwargs["update_fields"])
            if "test_name" in uf:
                uf.add("test_name_hash")
            if "loinc_code" in uf:
                uf.add("loinc_code_hash")
            kwargs["update_fields"] = uf

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.test_name} ({self.get_priority_display()}) — {self.patient.universal_id}"


class LabResult(TimeStampedModel):
    """A laboratory test result linked to an encounter."""

    encounter = models.ForeignKey(Encounter, on_delete=models.PROTECT, related_name="lab_results")
    order = models.OneToOneField(
        LabOrder,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="result",
        help_text="The originating order, if placed through the system.",
    )
    test_name = EncryptedCharField(max_length=200, verbose_name="Test name")
    test_name_hash = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        editable=False,
        help_text="HMAC-SHA256 blind index of test_name for exact-match querying.",
    )
    loinc_code = EncryptedCharField(
        max_length=20,
        blank=True,
        validators=[validate_loinc],
        verbose_name="LOINC code",
        help_text="Optional LOINC code for structured lab interoperability, e.g. 2160-0 (Creatinine).",
    )
    loinc_code_hash = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        editable=False,
        help_text="HMAC-SHA256 blind index of loinc_code for exact-match querying.",
    )
    result_value = EncryptedTextField(verbose_name="Result / findings")
    reference_range = models.CharField(max_length=100, blank=True, verbose_name="Reference range")
    is_abnormal = models.BooleanField(default=False)
    is_critical = models.BooleanField(
        default=False,
        verbose_name="Critical value",
        help_text="Flagged when result represents an immediate life-threatening critical value.",
    )
    performed_at = models.DateTimeField(null=True, blank=True, verbose_name="Date/time performed")
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="lab_results_created",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Lab Result"

    def save(self, *args, **kwargs):
        try:
            tn = str(self.test_name or "").strip()
            self.test_name_hash = make_blind_index(tn) if tn else ""
        except Exception:
            self.test_name_hash = ""
        try:
            lc = str(self.loinc_code or "").strip()
            self.loinc_code_hash = make_blind_index(lc) if lc else ""
        except Exception:
            self.loinc_code_hash = ""

        if "update_fields" in kwargs and kwargs["update_fields"] is not None:
            uf = set(kwargs["update_fields"])
            if "test_name" in uf:
                uf.add("test_name_hash")
            if "loinc_code" in uf:
                uf.add("loinc_code_hash")
            kwargs["update_fields"] = uf

        super().save(*args, **kwargs)

    def __str__(self):
        status = "Critical" if self.is_critical else ("Abnormal" if self.is_abnormal else "Normal")
        return f"{self.test_name} ({status})"


class VitalSign(TimeStampedModel):
    """
    Numeric vital signs — stored unencrypted to enable charting queries.
    One row per observation session (e.g. one set of vitals per shift).
    """

    encounter = models.ForeignKey(
        Encounter, on_delete=models.PROTECT, related_name="vitals", null=True, blank=True
    )
    patient = models.ForeignKey("patients.Patient", on_delete=models.PROTECT, related_name="vitals")
    recorded_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, related_name="vitals_recorded"
    )
    recorded_at = models.DateTimeField(default=timezone.now)

    # Clinical measurements — all nullable (record what was measured)
    temperature = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("30.0")), MaxValueValidator(Decimal("45.0"))],
        verbose_name="Temperature (°C)",
    )
    heart_rate = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(20), MaxValueValidator(300)],
        verbose_name="Heart rate (bpm)",
    )
    respiratory_rate = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(4), MaxValueValidator(80)],
        verbose_name="Respiratory rate (breaths/min)",
    )
    bp_systolic = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(50), MaxValueValidator(250)],
        verbose_name="BP systolic (mmHg)",
    )
    bp_diastolic = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(30), MaxValueValidator(150)],
        verbose_name="BP diastolic (mmHg)",
    )
    spo2 = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("50.0")), MaxValueValidator(Decimal("100.0"))],
        verbose_name="SpO2 (%)",
    )
    pain_score = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(10)],
        verbose_name="Pain score (0–10)",
    )
    weight_kg = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.5")), MaxValueValidator(Decimal("500.0"))],
        verbose_name="Weight (kg)",
    )
    height_cm = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("20.0")), MaxValueValidator(Decimal("300.0"))],
        verbose_name="Height (cm)",
    )
    blood_glucose = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.5")), MaxValueValidator(Decimal("50.0"))],
        verbose_name="Blood glucose (mmol/L)",
    )

    class Meta:
        ordering = ["-recorded_at"]
        verbose_name = "Vital Sign"
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(temperature__isnull=True)
                    | (models.Q(temperature__gte=30.0) & models.Q(temperature__lte=45.0))
                ),
                name="vitalsign_temperature_range",
            ),
            models.CheckConstraint(
                check=(
                    models.Q(heart_rate__isnull=True)
                    | (models.Q(heart_rate__gte=20) & models.Q(heart_rate__lte=300))
                ),
                name="vitalsign_heart_rate_range",
            ),
            models.CheckConstraint(
                check=(
                    models.Q(bp_systolic__isnull=True)
                    | (models.Q(bp_systolic__gte=50) & models.Q(bp_systolic__lte=250))
                ),
                name="vitalsign_bp_systolic_range",
            ),
            models.CheckConstraint(
                check=(
                    models.Q(bp_diastolic__isnull=True)
                    | (models.Q(bp_diastolic__gte=30) & models.Q(bp_diastolic__lte=150))
                ),
                name="vitalsign_bp_diastolic_range",
            ),
            models.CheckConstraint(
                check=(
                    models.Q(spo2__isnull=True) | (models.Q(spo2__gte=50) & models.Q(spo2__lte=100))
                ),
                name="vitalsign_spo2_range",
            ),
            models.CheckConstraint(
                check=(
                    models.Q(pain_score__isnull=True)
                    | (models.Q(pain_score__gte=0) & models.Q(pain_score__lte=10))
                ),
                name="vitalsign_pain_score_range",
            ),
            models.CheckConstraint(
                check=(
                    models.Q(blood_glucose__isnull=True)
                    | (
                        models.Q(blood_glucose__gte=Decimal("0.5"))
                        & models.Q(blood_glucose__lte=Decimal("50.0"))
                    )
                ),
                name="vitalsign_blood_glucose_range",
            ),
        ]

    def clean(self):
        super().clean()
        if (
            self.bp_systolic is not None
            and self.bp_diastolic is not None
            and self.bp_systolic <= self.bp_diastolic
        ):
            raise ValidationError(
                {
                    "bp_systolic": "Systolic blood pressure must be greater than diastolic blood pressure."
                }
            )

    def __str__(self):
        return f"Vitals {self.patient.universal_id} @ {self.recorded_at.strftime('%Y-%m-%d %H:%M')}"


class PatientDocument(TimeStampedModel):
    """A clinical document attached to a patient (X-ray image, consent form, discharge summary, etc.)."""

    ConfidentialityLevel = ConfidentialityLevel

    patient = models.ForeignKey(
        "patients.Patient", on_delete=models.PROTECT, related_name="documents"
    )
    uploaded_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="documents_uploaded",
    )
    file = models.FileField(upload_to="patient_documents/%Y/%m/")
    original_name = models.CharField(max_length=255, verbose_name="Original file name")
    file_type = models.CharField(max_length=100, blank=True, verbose_name="MIME type")
    file_size = models.PositiveIntegerField(default=0, verbose_name="File size (bytes)")
    description = models.CharField(max_length=255, blank=True, verbose_name="Description")
    confidentiality = models.CharField(
        max_length=20,
        choices=ConfidentialityLevel.choices,
        default=ConfidentialityLevel.NORMAL,
        db_index=True,
        help_text="Data sensitivity tier under Act 843 §37 / ISO 22600.",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Patient Document"

    def __str__(self):
        return f"{self.original_name} — {self.patient.universal_id}"


class MedicationAdministration(TimeStampedModel):
    """Medication Administration Record (MAR) entry — one scheduled dose."""

    class Status(models.TextChoices):
        DUE = "due", "Due"
        GIVEN = "given", "Given"
        HELD = "held", "Held"
        REFUSED = "refused", "Refused by Patient"
        MISSED = "missed", "Missed"

    prescription = models.ForeignKey(
        Prescription, on_delete=models.CASCADE, related_name="administrations"
    )
    administered_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="medications_administered",
    )
    scheduled_time = models.DateTimeField()
    administered_time = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DUE)
    notes = EncryptedTextField(blank=True)

    class Meta:
        ordering = ["scheduled_time"]
        verbose_name = "Medication Administration"
        verbose_name_plural = "Medication Administrations"
        indexes = [
            models.Index(fields=["status", "scheduled_time"], name="medadmin_status_scheduled_idx"),
        ]

    def __str__(self):
        return (
            f"{self.prescription.drug_name} — "
            f"{self.get_status_display()} @ {self.scheduled_time.strftime('%Y-%m-%d %H:%M')}"
        )
