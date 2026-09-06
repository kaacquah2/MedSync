"""
Append-only Audit Log with tamper-evident hash chain.

Every access to — and modification of — patient data is recorded here.
Entries can NEVER be edited or deleted, enforced at three layers:
  1. Python  — save() raises if pk exists; delete() always raises.
  2. Database— a BEFORE UPDATE OR DELETE trigger (Postgres only) raises an
               exception at the DB level so app-layer bugs can't bypass it.
  3. Hash chain — each row records sha256(prev_row_hash + canonical_fields)
                  so tampering with any row breaks the chain from that point.
                  Verify with: python manage.py verify_audit_chain

Key field:
  is_cross_hospital — True when the accessing clinician's home hospital
  differs from the hospital that created the record being accessed.
  This is the "inter-hospital access flagging" feature.
"""

import hashlib
import json

from django.db import models
from django.utils import timezone


class AuditLogQuerySet(models.QuerySet):
    """Custom QuerySet with compliance reporting helpers."""

    def cross_hospital(self):
        """Filter entries flagged for cross-hospital access."""
        return self.filter(is_cross_hospital=True)

    def break_glass(self):
        """Filter break-glass access entries."""
        return self.filter(action="BREAK_GLASS")

    def compliance_report(self, hospital=None, date_from=None, date_to=None):
        """Filter audit logs for compliance reporting by hospital and date range."""
        qs = self
        if hospital:
            qs = qs.filter(models.Q(actor_hospital=hospital) | models.Q(is_cross_hospital=True))
        if date_from:
            qs = qs.filter(timestamp__date__gte=date_from)
        if date_to:
            qs = qs.filter(timestamp__date__lte=date_to)
        return qs


class AuditLog(models.Model):
    """Immutable audit log entry."""

    objects = AuditLogQuerySet.as_manager()

    class Action(models.TextChoices):
        LOGIN = "LOGIN", "Login"
        LOGOUT = "LOGOUT", "Logout"
        VIEW_PATIENT = "VIEW_PATIENT", "View Patient"
        CREATE_PATIENT = "CREATE_PATIENT", "Create Patient"
        UPDATE_PATIENT = "UPDATE_PATIENT", "Update Patient"
        VIEW_ENCOUNTER = "VIEW_ENCOUNTER", "View Encounter"
        CREATE_ENCOUNTER = "CREATE_ENCOUNTER", "Create Encounter"
        CREATE_DIAGNOSIS = "CREATE_DIAGNOSIS", "Create Diagnosis"
        CREATE_PRESCRIPTION = "CREATE_PRESCRIPTION", "Create Prescription"
        CREATE_LAB_RESULT = "CREATE_LAB_RESULT", "Create Lab Result"
        ACCESS_DENIED = "ACCESS_DENIED", "Access Denied"
        PASSWORD_CHANGE = "PASSWORD_CHANGE", "Password Change"
        MFA_ENROLLED = "MFA_ENROLLED", "MFA Enrolled"
        MFA_VERIFIED = "MFA_VERIFIED", "MFA Verified"
        MFA_REMOVED = "MFA_REMOVED", "MFA Device Removed"
        # Search
        SEARCH_PATIENT = "SEARCH_PATIENT", "Patient Search"
        # Patient alerts / allergies
        CREATE_ALERT = "CREATE_ALERT", "Alert/Allergy Created"
        DEACTIVATE_ALERT = "DEACTIVATE_ALERT", "Alert/Allergy Deactivated"
        # Inter-hospital access control
        BREAK_GLASS = "BREAK_GLASS", "Break-Glass Override"
        TREATMENT_REL_STARTED = "TREATMENT_REL_STARTED", "Treatment Relationship Started"
        CONSENT_GRANTED = "CONSENT_GRANTED", "Patient Consent Granted"
        # Account security
        RECOVERY_CODES_REGENERATED = "RECOVERY_CODES_REGENERATED", "Recovery Codes Regenerated"
        SESSIONS_REVOKED = "SESSIONS_REVOKED", "Sessions Revoked (Sign Out Everywhere)"
        # Staff lifecycle
        STAFF_DEACTIVATED = "STAFF_DEACTIVATED", "Staff Account Deactivated"
        STAFF_ACTIVATED = "STAFF_ACTIVATED", "Staff Account Activated"
        # Vitals
        CREATE_VITAL = "CREATE_VITAL", "Vital Signs Recorded"
        # Lab orders
        CREATE_LAB_ORDER = "CREATE_LAB_ORDER", "Lab Order Created"
        UPDATE_LAB_ORDER = "UPDATE_LAB_ORDER", "Lab Order Updated"
        # Medication administration
        ADMINISTER_MEDICATION = "ADMINISTER_MEDICATION", "Medication Administered"
        # Appointments
        CREATE_APPOINTMENT = "CREATE_APPOINTMENT", "Appointment Created"
        UPDATE_APPOINTMENT = "UPDATE_APPOINTMENT", "Appointment Status Updated"
        # Referrals
        CREATE_REFERRAL = "CREATE_REFERRAL", "Referral Created"
        UPDATE_REFERRAL = "UPDATE_REFERRAL", "Referral Status Updated"
        # Shift / handover
        START_SHIFT = "START_SHIFT", "Shift Started"
        END_SHIFT = "END_SHIFT", "Shift Ended"
        CREATE_HANDOVER = "CREATE_HANDOVER", "Handover Note Created"
        # AI query
        AI_QUERY = "AI_QUERY", "AI Patient Query"
        # Export
        EXPORT_PDF = "EXPORT_PDF", "Patient PDF Export"
        # Security
        VALIDATE_AUDIT_CHAIN = "VALIDATE_AUDIT_CHAIN", "Audit Chain Validated"
        # Staff password management
        RESET_STAFF_PASSWORD = "RESET_STAFF_PASSWORD", "Staff Password Reset"
        # Patient documents
        UPLOAD_DOCUMENT = "UPLOAD_DOCUMENT", "Document Uploaded"
        DOWNLOAD_DOCUMENT = "DOWNLOAD_DOCUMENT", "Document Downloaded"
        DELETE_DOCUMENT = "DELETE_DOCUMENT", "Document Deleted"
        LIST_DOCUMENTS = "LIST_DOCUMENTS", "Documents Listed"
        ACKNOWLEDGE_HANDOVER = "ACKNOWLEDGE_HANDOVER", "Handover Acknowledged"

    # Actor (nullable so we can log failed / pre-auth attempts)
    actor = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    actor_username = models.CharField(max_length=150, blank=True)
    actor_role = models.CharField(max_length=20, blank=True)
    actor_hospital = models.CharField(max_length=200, blank=True)

    # Action
    action = models.CharField(max_length=30, choices=Action.choices)
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)

    # Target
    target_type = models.CharField(max_length=50, blank=True)
    target_id = models.CharField(max_length=50, blank=True)
    patient_nhid = models.CharField(
        max_length=20,
        blank=True,
        db_index=True,
        verbose_name="Patient NHID",
    )

    # Cross-hospital flag
    is_cross_hospital = models.BooleanField(
        default=False,
        help_text="True if accessing clinician's hospital differs from the record's origin hospital.",
    )

    # Request metadata
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    extra = models.JSONField(default=dict, blank=True)

    # ── Hash-chain tamper evidence ────────────────────────────────────────
    # prev_hash: row_hash of the immediately preceding AuditLog entry (by pk).
    #            Empty string for the very first row.
    # row_hash:  sha256(prev_hash + canonical_json_of_this_row)
    # Both are set by audit.utils.log_action before save().
    prev_hash = models.CharField(max_length=64, blank=True, editable=False)
    row_hash = models.CharField(max_length=64, blank=True, editable=False, db_index=True)

    class Meta:
        ordering = ["-timestamp"]
        verbose_name = "Audit Log Entry"
        verbose_name_plural = "Audit Log"
        indexes = [
            models.Index(fields=["actor_hospital", "timestamp"], name="audit_log_hosp_ts_idx"),
            models.Index(fields=["action", "timestamp"], name="audit_log_action_ts_idx"),
        ]

    def __str__(self):
        return f"[{self.timestamp:%Y-%m-%d %H:%M}] {self.actor_username} — {self.action}"

    # ── Append-only enforcement ───────────────────────────────────────────

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError("AuditLog entries are immutable and cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("AuditLog entries cannot be deleted.")

    # ── Hash-chain helpers ────────────────────────────────────────────────

    @classmethod
    def compute_row_hash(cls, prev_hash: str, fields: dict) -> str:
        """
        Compute sha256(prev_hash + canonical_json(fields)).

        Canonical JSON uses sort_keys=True and compact separators=(',', ':')
        to ensure stable, platform-independent serialization.
        """
        canonical = json.dumps(fields, sort_keys=True, default=str, separators=(",", ":"))
        payload = ((prev_hash or "") + canonical).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    @classmethod
    def _chain_fields_for(cls, entry) -> dict:
        """Return the canonical field dict used when computing this entry's hash."""
        return {
            "actor_username": str(entry.actor_username or ""),
            "actor_role": str(entry.actor_role or ""),
            "actor_hospital": str(entry.actor_hospital or ""),
            "action": str(entry.action or ""),
            "timestamp": entry.timestamp.isoformat() if entry.timestamp else "",
            "target_type": str(entry.target_type or ""),
            "target_id": str(entry.target_id or ""),
            "patient_nhid": str(entry.patient_nhid or ""),
            "is_cross_hospital": bool(entry.is_cross_hospital),
            "ip_address": str(entry.ip_address or ""),
            "extra": entry.extra if isinstance(entry.extra, dict) else {},
        }


class AuditLogReview(models.Model):
    """Stores the reviewed state of an immutable AuditLog entry."""

    audit_log = models.OneToOneField(
        "audit.AuditLog",
        on_delete=models.CASCADE,
        related_name="review",
    )
    reviewed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    reviewed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Audit Log Review"
        verbose_name_plural = "Audit Log Reviews"

    def __str__(self):
        return f"Review of AuditLog #{self.audit_log_id} by {self.reviewed_by.username if self.reviewed_by else 'Unknown'}"


class AuditLogArchiveAnchor(models.Model):
    """
    Stores the cryptographic anchor and file validation properties for a pruned range
    of historical audit logs archived in offline WORM storage.
    """
    archive_filename = models.CharField(max_length=255, unique=True)
    last_row_pk = models.PositiveIntegerField(unique=True)
    last_row_hash = models.CharField(max_length=64)
    archive_file_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Audit Log Archive Anchor"
        verbose_name_plural = "Audit Log Archive Anchors"
        ordering = ["last_row_pk"]

    def __str__(self):
        return f"ArchiveAnchor({self.archive_filename}, PK={self.last_row_pk})"

