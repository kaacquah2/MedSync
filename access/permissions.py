"""
Central patient-record access authorization.

A single function — can_access_patient() — is the chokepoint for all
inter-hospital record access decisions.  Views call it and act on the result.

Access evaluation order (break-glass deliberately overrides consent):
  1. admin                  — SYSTEM_ADMIN or HOSPITAL_ADMIN (unrestricted read)
  2. break_glass            — unexpired BreakGlassAccess grant (emergency override)
  3. consent-revoked        — explicitly revoked PatientConsent denies access
  4. same_hospital          — clinician's home hospital == patient's registering hospital
  5. treatment_relationship — active TreatmentRelationship exists
  6. consent-granted        — active PatientConsent exists

Otherwise: denied.

Note: this function answers "can this user see this patient at all?".
Role-based sub-permissions (e.g. only DOCTOR can prescribe) remain in the
view layer via the existing RoleRequiredMixin / @role_required decorator.
"""

import logging
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)

AccessBasis = Literal[
    "same_hospital",
    "treatment_relationship",
    "break_glass",
    "admin",
    "denied",
    "error",  # unexpected exception — always treated as denied
    "patient_consent",
]


@dataclass
class AccessDecision:
    allowed: bool
    basis: AccessBasis

    def __bool__(self):
        return self.allowed


def can_access_patient(user, patient) -> AccessDecision:
    """
    Return an AccessDecision describing whether *user* may access *patient*.

    Evaluates gates in priority order:
      admin → break_glass → consent-revoked → same_hospital → treatment_relationship → consent-granted → denied

    FAIL-CLOSED: any unexpected exception (DB error, attribute error, etc.)
    returns AccessDecision(allowed=False, basis="error") and logs the error.
    The gate never grants access on error.
    """
    try:
        return _can_access_patient_inner(user, patient)
    except Exception:
        logger.exception(
            "Unexpected exception in can_access_patient — denying access "
            "(user_id=%s, patient_id=%s)",
            getattr(user, "pk", "?"),
            getattr(patient, "pk", "?"),
        )
        return AccessDecision(allowed=False, basis="error")


def _can_access_patient_inner(user, patient) -> AccessDecision:
    """Inner implementation — exceptions propagate to the fail-closed wrapper."""
    from .models import BreakGlassAccess, PatientConsent, TreatmentRelationship

    if not getattr(user, "is_authenticated", False):
        return AccessDecision(allowed=False, basis="denied")

    # 1. Admin override — super_admin has unrestricted national access;
    # hospital_admin is strictly tenant-scoped to their own hospital's patients.
    if (
        getattr(user, "is_super_admin", False)
        or getattr(user, "role", None) == "super_admin"
        or getattr(user, "is_superuser", False)
    ):
        return AccessDecision(allowed=True, basis="admin")

    if getattr(user, "is_hospital_admin", False) or getattr(user, "role", None) == "hospital_admin":
        if (
            user.hospital is not None
            and patient.registered_at_hospital is not None
            and user.hospital_id == patient.registered_at_hospital_id
        ):
            return AccessDecision(allowed=True, basis="admin")
        return AccessDecision(allowed=False, basis="denied")

    # 2. Unexpired break-glass grant (always overrides consent)
    if BreakGlassAccess.objects.active_for(user, patient).exists():
        return AccessDecision(allowed=True, basis="break_glass")

    # 3. Check for explicitly revoked consent
    if user.hospital is not None:
        consent = PatientConsent.objects.filter(patient=patient, hospital=user.hospital).first()
        if consent and (not consent.granted or consent.revoked_at is not None):
            return AccessDecision(allowed=False, basis="denied")

    # 4. Same-hospital — patient was registered at the clinician's home hospital
    if (
        user.hospital is not None
        and patient.registered_at_hospital is not None
        and user.hospital_id == patient.registered_at_hospital_id
    ):
        return AccessDecision(allowed=True, basis="same_hospital")

    # 5. Active treatment relationship
    if TreatmentRelationship.objects.active_for(user, patient).exists():
        return AccessDecision(allowed=True, basis="treatment_relationship")

    # 6. Patient Consent explicitly granted
    if user.hospital is not None:
        consent = PatientConsent.objects.filter(patient=patient, hospital=user.hospital).first()
        if consent and consent.granted and consent.revoked_at is None:
            return AccessDecision(allowed=True, basis="patient_consent")

    return AccessDecision(allowed=False, basis="denied")


def ensure_treatment_relationship(clinician, patient, hospital, reason="Encounter opened"):
    """
    Idempotently ensure an active TreatmentRelationship exists for this
    clinician+patient pair.

    Called when a clinician creates an encounter so that subsequent visits
    don't trigger a break-glass prompt for ongoing care.
    """
    from .models import TreatmentRelationship

    if not TreatmentRelationship.objects.active_for(clinician, patient).exists():
        rel = TreatmentRelationship.objects.create(
            clinician=clinician,
            patient=patient,
            hospital=hospital,
            reason=reason,
        )
        return rel
    return None
