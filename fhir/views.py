"""
FHIR R4 read-only API endpoints.

GET /fhir/metadata                      → FHIR CapabilityStatement (no auth required)
GET /fhir/Patient/<nhid>/          → FHIR Patient resource (JSON)
GET /fhir/Patient/<nhid>/$everything → FHIR Bundle with full record

Access gate:
  - RBAC: requires clinical (doctor, nurse, lab_technician) or admin (super_admin, hospital_admin) role.
  - Inter-hospital gate: uses the same can_access_patient() decision function as the rest of the app
    (evaluates admin, active break-glass grants, consent, same-hospital, treatment relationship).
  - Every fetch (and access denial) is audited as VIEW_PATIENT or ACCESS_DENIED.
  - /fhir/metadata is intentionally unauthenticated (FHIR R4 conformance requirement).

Read-only enforcement:
  - Restricted to HTTP GET (@require_GET). Any attempt to POST, PUT, PATCH, or DELETE returns HTTP 405.
"""

from django.conf import settings as django_settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET
from rest_framework.throttling import ScopedRateThrottle

from access.permissions import can_access_patient
from audit.utils import log_action
from patients.models import Patient

from .mappers import patient_everything, patient_to_fhir


def _check_fhir_throttle(request, scope: str):
    """Check ScopedRateThrottle for function-based FHIR view."""
    throttle = ScopedRateThrottle()
    throttle.scope = scope
    if not throttle.allow_request(request, None):
        wait = throttle.wait()
        return False, _fhir_error(
            429,
            "throttled",
            f"Rate limit exceeded. Try again in {int(wait or 60)} seconds.",
        )
    return True, None


def _fhir_json(data, status=200) -> JsonResponse:
    return JsonResponse(
        data,
        status=status,
        content_type="application/fhir+json",
        json_dumps_params={"indent": 2},
    )


def _fhir_error(status: int, code: str, message: str) -> JsonResponse:
    return _fhir_json(
        {
            "resourceType": "OperationOutcome",
            "issue": [
                {
                    "severity": "error",
                    "code": code,
                    "diagnostics": message,
                }
            ],
        },
        status=status,
    )


@require_GET
def capability_statement(request) -> JsonResponse:
    """
    GET /fhir/metadata

    Returns a minimal FHIR R4 CapabilityStatement describing the server's
    capabilities. Intentionally unauthenticated per FHIR R4 spec (§3.1.0.1):
    connecting systems must be able to discover capabilities before auth.
    """
    fhir_base = getattr(django_settings, "FHIR_BASE_URL", "https://emr.example.com/fhir")
    statement = {
        "resourceType": "CapabilityStatement",
        "id": "mEd-capability",
        "status": "active",
        "kind": "instance",
        "fhirVersion": "4.0.1",
        "format": ["application/fhir+json"],
        "implementation": {
            "description": "mEd Secure EMR FHIR R4 Interface",
            "url": fhir_base,
        },
        "rest": [
            {
                "mode": "server",
                "security": {
                    "description": "Session-based authentication required for all resources except /metadata.",
                },
                "resource": [
                    {
                        "type": "Patient",
                        "interaction": [{"code": "read"}],
                        "operation": [
                            {
                                "name": "everything",
                                "definition": "http://hl7.org/fhir/OperationDefinition/Patient-everything",
                            }
                        ],
                    }
                ],
            }
        ],
    }
    return _fhir_json(statement)


def _check_fhir_authorization(request, patient):
    """
    Check authorization for accessing FHIR patient record resources.

    Returns (True, None) if authorized, or (False, JsonResponse) if denied.
    """
    # 1. RBAC check: User must be clinical or admin-level
    if not (
        getattr(request.user, "is_clinical", False)
        or getattr(request.user, "is_admin_level", False)
    ):
        log_action(
            request,
            action="ACCESS_DENIED",
            target=patient,
            patient=patient,
            is_cross_hospital=False,
            extra={"fhir": True, "reason": "non_clinical_role"},
        )
        return False, _fhir_error(
            403, "forbidden", "Role not authorized for clinical FHIR exports."
        )

    # 2. Inter-hospital access gate (same-hospital, break-glass, treatment relationship, consent, admin)
    decision = can_access_patient(request.user, patient)
    if not decision:
        log_action(
            request,
            action="ACCESS_DENIED",
            target=patient,
            patient=patient,
            is_cross_hospital=True,
            extra={"fhir": True, "basis": decision.basis},
        )
        return False, _fhir_error(403, "forbidden", "Insufficient access to this patient record.")

    return True, None


@login_required
@require_GET
def patient_resource(request, universal_id: str) -> JsonResponse:
    """
    GET /fhir/Patient/<nhid>/

    Returns the FHIR R4 Patient resource for the given NHID.
    Access-gated by RBAC + break-glass logic; every fetch is audited.
    """
    throttled, error_response = _check_fhir_throttle(request, "fhir_resource")
    if not throttled:
        return error_response

    patient = get_object_or_404(Patient, universal_id=universal_id)

    authorized, error_response = _check_fhir_authorization(request, patient)
    if not authorized:
        return error_response

    is_cross = (
        request.user.hospital is not None
        and patient.registered_at_hospital_id is not None
        and request.user.hospital_id != patient.registered_at_hospital_id
    )
    log_action(
        request,
        action="VIEW_PATIENT",
        target=patient,
        patient=patient,
        is_cross_hospital=is_cross,
        extra={"fhir": True},
    )

    return _fhir_json(patient_to_fhir(patient))


@login_required
@require_GET
def patient_everything_endpoint(request, universal_id: str) -> JsonResponse:
    """
    GET /fhir/Patient/<nhid>/$everything

    Returns a FHIR Bundle with the patient's complete record:
    Patient + Encounters + Conditions + MedicationRequests + Observations.
    Access-gated by RBAC + break-glass logic; every fetch is audited.
    """
    throttled, error_response = _check_fhir_throttle(request, "fhir_everything")
    if not throttled:
        return error_response

    patient = get_object_or_404(Patient, universal_id=universal_id)

    authorized, error_response = _check_fhir_authorization(request, patient)
    if not authorized:
        return error_response

    is_cross = (
        request.user.hospital is not None
        and patient.registered_at_hospital_id is not None
        and request.user.hospital_id != patient.registered_at_hospital_id
    )
    log_action(
        request,
        action="VIEW_PATIENT",
        target=patient,
        patient=patient,
        is_cross_hospital=is_cross,
        extra={"fhir": True, "operation": "$everything"},
    )

    encounters_qs = (
        patient.encounters.select_related("created_by", "created_at_hospital")
        .prefetch_related("diagnoses", "prescriptions", "lab_results")
        .order_by("created_at")
    )

    bundle = patient_everything(patient, encounters_qs)
    return _fhir_json(bundle)
