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
  LabOrder.test_name is unencrypted to allow SQL-level worklist filtering by test type
  (e.g. "show all pending CBC orders"). Once a result is recorded, LabResult.test_name
  is encrypted as PHI. This asymmetry is intentional: order metadata is operational,
  result content is clinical.

Each record is stamped with:
  - created_by          : the clinician who created it
  - created_at_hospital : the hospital where the encounter occurred

This stamp is what enables the audit layer to detect cross-hospital access
(actor.hospital ≠ created_at_hospital on a subsequent access).
"""

from django.db import models
from django.utils import timezone

from core.fields import EncryptedCharField, EncryptedTextField
from core.models import TimeStampedModel
from records.validators import (
    validate_icd10,
    validate_loinc,
    validate_rxnorm,
    validate_snomed,
)


class Encounter(TimeStampedModel):
    """A clinical visit / contact between a patient and a facility."""

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

    encounter = models.ForeignKey(Encounter, on_delete=models.CASCADE, related_name="diagnoses")
    icd_code = models.CharField(
        max_length=20,
        blank=True,
        validators=[validate_icd10],
        verbose_name="ICD-10 code",
        help_text="ICD-10-CM code, e.g. J18.9 (Pneumonia, unspecified).",
    )
    snomed_code = models.CharField(
        max_length=20,
        blank=True,
        validators=[validate_snomed],
        verbose_name="SNOMED CT code",
        help_text="Optional SNOMED CT concept ID for interoperability.",
    )
    description = EncryptedTextField(verbose_name="Diagnosis description")
    is_primary = models.BooleanField(default=True)
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

    encounter = models.ForeignKey(Encounter, on_delete=models.CASCADE, related_name="prescriptions")
    drug_name = EncryptedCharField(max_length=200, verbose_name="Drug / Medication name")
    rxnorm_code = models.CharField(
        max_length=20,
        blank=True,
        validators=[validate_rxnorm],
        verbose_name="RxNorm code",
        help_text="Optional RxNorm CUI for structured medication interoperability.",
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
        Encounter, on_delete=models.CASCADE, related_name="lab_orders", null=True, blank=True
    )
    patient = models.ForeignKey(
        "patients.Patient", on_delete=models.PROTECT, related_name="lab_orders"
    )
    ordered_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, related_name="lab_orders_created"
    )
    # Intentionally stored as plaintext to allow SQL-level worklist filtering
    # (e.g. "show all pending CBC orders"). This is operational metadata, not PHI.
    # Contrast with LabResult.test_name which IS encrypted because it forms part
    # of the clinical finding and must be treated as PHI.
    test_name = models.CharField(max_length=200, verbose_name="Test name")
    loinc_code = models.CharField(
        max_length=20,
        blank=True,
        validators=[validate_loinc],
        verbose_name="LOINC code",
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

    def __str__(self):
        return f"{self.test_name} ({self.get_priority_display()}) — {self.patient.universal_id}"


class LabResult(TimeStampedModel):
    """A laboratory test result linked to an encounter."""

    encounter = models.ForeignKey(Encounter, on_delete=models.CASCADE, related_name="lab_results")
    order = models.OneToOneField(
        LabOrder,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="result",
        help_text="The originating order, if placed through the system.",
    )
    test_name = EncryptedCharField(max_length=200, verbose_name="Test name")
    loinc_code = models.CharField(
        max_length=20,
        blank=True,
        validators=[validate_loinc],
        verbose_name="LOINC code",
        help_text="Optional LOINC code for structured lab interoperability, e.g. 2160-0 (Creatinine).",
    )
    result_value = EncryptedTextField(verbose_name="Result / findings")
    reference_range = models.CharField(max_length=100, blank=True, verbose_name="Reference range")
    is_abnormal = models.BooleanField(default=False)
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

    def __str__(self):
        return f"{self.test_name} ({'Abnormal' if self.is_abnormal else 'Normal'})"


class VitalSign(TimeStampedModel):
    """
    Numeric vital signs — stored unencrypted to enable charting queries.
    One row per observation session (e.g. one set of vitals per shift).
    """

    encounter = models.ForeignKey(
        Encounter, on_delete=models.CASCADE, related_name="vitals", null=True, blank=True
    )
    patient = models.ForeignKey("patients.Patient", on_delete=models.PROTECT, related_name="vitals")
    recorded_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, related_name="vitals_recorded"
    )
    recorded_at = models.DateTimeField(default=timezone.now)

    # Clinical measurements — all nullable (record what was measured)
    temperature = models.DecimalField(
        max_digits=4, decimal_places=1, null=True, blank=True, verbose_name="Temperature (°C)"
    )
    heart_rate = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name="Heart rate (bpm)"
    )
    respiratory_rate = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name="Respiratory rate (breaths/min)"
    )
    bp_systolic = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name="BP systolic (mmHg)"
    )
    bp_diastolic = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name="BP diastolic (mmHg)"
    )
    spo2 = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True, verbose_name="SpO2 (%)"
    )
    pain_score = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name="Pain score (0–10)"
    )
    weight_kg = models.DecimalField(
        max_digits=5, decimal_places=1, null=True, blank=True, verbose_name="Weight (kg)"
    )
    height_cm = models.DecimalField(
        max_digits=5, decimal_places=1, null=True, blank=True, verbose_name="Height (cm)"
    )

    class Meta:
        ordering = ["-recorded_at"]
        verbose_name = "Vital Sign"

    def __str__(self):
        return f"Vitals {self.patient.universal_id} @ {self.recorded_at.strftime('%Y-%m-%d %H:%M')}"


class PatientDocument(TimeStampedModel):
    """A clinical document attached to a patient (X-ray image, consent form, discharge summary, etc.)."""

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
