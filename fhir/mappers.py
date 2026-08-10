"""
FHIR R4 resource mappers.

Maps internal mEd model instances to HL7 FHIR R4 JSON representations.

Scope:
  - Patient     → FHIR Patient
  - Encounter   → FHIR Encounter
  - Diagnosis   → FHIR Condition
  - Prescription→ FHIR MedicationRequest
  - LabResult   → FHIR Observation

This is a read-only export layer for interoperability demonstration.
Full FHIR conformance (CapabilityStatement, search parameters, subscriptions)
is out of scope for this prototype — see ADR: fhir-adoption.

All dates are serialised as UTC ISO-8601 strings. PHI in encrypted fields
(first_name, diagnoses, etc.) is decrypted at the Python layer by the Fernet
EncryptedCharField.from_db_value() descriptor before reaching this module.
"""

from django.conf import settings

# ── Base URL and Identifier helpers ────────────────────────────────────────


def _base_url() -> str:
    """Return the FHIR base URL (configurable via FHIR_BASE_URL setting)."""
    return getattr(settings, "FHIR_BASE_URL", "https://emr.example.com/fhir")


def _ref(resource_type: str, identifier: str) -> dict:
    return {"reference": f"{resource_type}/{identifier}"}


def _iso(dt) -> str | None:
    if dt is None:
        return None
    return dt.isoformat() if hasattr(dt, "isoformat") else str(dt)


# ── Patient ───────────────────────────────────────────────────────────────


def patient_to_fhir(patient) -> dict:
    """
    Map a patients.Patient to a FHIR R4 Patient resource.

    Identifiers:
      - The mEd NHID is mapped to system 'urn:oid:emr.nhid'
      - The national ID (Ghana Card) is mapped to 'urn:oid:gh.national-id'
    """
    resource = {
        "resourceType": "Patient",
        "id": patient.universal_id,
        "meta": {"source": f"{_base_url()}/Patient/{patient.universal_id}"},
        "identifier": [
            {
                "use": "official",
                "system": "urn:oid:emr.nhid",
                "value": patient.universal_id,
            }
        ],
        "name": [
            {
                "use": "official",
                "family": str(patient.last_name),
                "given": [str(patient.first_name)],
            }
        ],
        "gender": {
            "M": "male",
            "F": "female",
            "O": "other",
        }.get(patient.sex, "unknown"),
        "birthDate": str(patient.date_of_birth) if patient.date_of_birth else None,
        "telecom": [],
        "address": [],
    }

    # National ID (Ghana Card)
    national_id = str(patient.national_id or "").strip()
    if national_id:
        resource["identifier"].append(
            {
                "use": "secondary",
                "system": "urn:oid:gh.national-id",
                "value": national_id,
            }
        )

    # Phone
    phone = str(patient.phone or "").strip()
    if phone:
        resource["telecom"].append({"system": "phone", "value": phone})

    # Email
    email = str(patient.email or "").strip()
    if email:
        resource["telecom"].append({"system": "email", "value": email})

    # Address
    address = str(patient.address or "").strip()
    if address:
        resource["address"].append({"text": address})

    # Managing organisation (registering hospital)
    if patient.registered_at_hospital_id:
        resource["managingOrganization"] = _ref(
            "Organization", f"HOSP-{patient.registered_at_hospital_id}"
        )

    return resource


# ── Encounter ─────────────────────────────────────────────────────────────

_ENCOUNTER_TYPE_MAP = {
    "OPD": ("AMB", "ambulatory"),
    "IPD": ("IMP", "inpatient encounter"),
    "EMRG": ("EMER", "emergency"),
    "FU": ("AMB", "ambulatory"),
    "TM": ("VR", "virtual"),
}


def encounter_to_fhir(encounter) -> dict:
    """Map a records.Encounter to a FHIR R4 Encounter resource."""
    code, display = _ENCOUNTER_TYPE_MAP.get(encounter.encounter_type, ("AMB", "ambulatory"))

    enc_id = f"ENC-{encounter.pk}"
    resource = {
        "resourceType": "Encounter",
        "id": enc_id,
        "status": "finished",
        "class": {
            "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
            "code": code,
            "display": display,
        },
        "subject": _ref("Patient", encounter.patient.universal_id),
        "period": {
            "start": _iso(encounter.created_at),
        },
        "reasonCode": [
            {
                "text": str(encounter.chief_complaint or ""),
            }
        ],
    }

    if encounter.created_at_hospital_id:
        resource["serviceProvider"] = _ref("Organization", f"HOSP-{encounter.created_at_hospital_id}")

    if encounter.created_by_id:
        resource["participant"] = [
            {
                "individual": _ref("Practitioner", f"PRAC-{encounter.created_by_id}"),
            }
        ]

    return resource


# ── Diagnosis → Condition ─────────────────────────────────────────────────


def diagnosis_to_fhir(diagnosis) -> dict:
    """Map a records.Diagnosis to a FHIR R4 Condition resource."""
    coding = []

    if diagnosis.icd_code:
        coding.append(
            {
                "system": "http://hl7.org/fhir/sid/icd-10",
                "code": diagnosis.icd_code,
                "display": str(diagnosis.description)[:100],
            }
        )

    if diagnosis.snomed_code:
        coding.append(
            {
                "system": "http://snomed.info/sct",
                "code": diagnosis.snomed_code,
            }
        )

    cond_id = f"COND-{diagnosis.pk}"
    resource = {
        "resourceType": "Condition",
        "id": cond_id,
        "subject": _ref("Patient", diagnosis.encounter.patient.universal_id),
        "encounter": _ref("Encounter", f"ENC-{diagnosis.encounter_id}"),
        "code": {
            "coding": coding,
            "text": str(diagnosis.description),
        },
        "category": [
            {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/condition-category",
                        "code": "encounter-diagnosis",
                        "display": "Encounter Diagnosis",
                    }
                ]
            }
        ],
        "clinicalStatus": {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                    "code": "active",
                }
            ]
        },
        "recordedDate": _iso(diagnosis.created_at),
    }

    if diagnosis.created_by_id:
        resource["recorder"] = _ref("Practitioner", f"PRAC-{diagnosis.created_by_id}")

    return resource


# ── Prescription → MedicationRequest ─────────────────────────────────────


def prescription_to_fhir(prescription) -> dict:
    """Map a records.Prescription to a FHIR R4 MedicationRequest resource."""
    coding = []
    if prescription.rxnorm_code:
        coding = [
            {
                "system": "http://www.nlm.nih.gov/research/umls/rxnorm",
                "code": prescription.rxnorm_code,
                "display": str(prescription.drug_name),
            }
        ]

    med_id = f"MED-{prescription.pk}"
    dosage_entry = {
        "text": f"{prescription.dosage} — {prescription.frequency}",
    }
    instructions = str(prescription.instructions or "").strip()
    if instructions:
        dosage_entry["patientInstruction"] = instructions

    resource = {
        "resourceType": "MedicationRequest",
        "id": med_id,
        "status": "active",
        "intent": "order",
        "subject": _ref("Patient", prescription.encounter.patient.universal_id),
        "encounter": _ref("Encounter", f"ENC-{prescription.encounter_id}"),
        "medicationCodeableConcept": {
            "coding": coding,
            "text": str(prescription.drug_name),
        },
        "dosageInstruction": [dosage_entry],
        "authoredOn": _iso(prescription.created_at),
    }

    if prescription.created_by_id:
        resource["requester"] = _ref("Practitioner", f"PRAC-{prescription.created_by_id}")

    return resource


# ── LabResult → Observation ───────────────────────────────────────────────


def lab_result_to_fhir(lab_result) -> dict:
    """Map a records.LabResult to a FHIR R4 Observation resource."""
    coding = []
    if lab_result.loinc_code:
        coding = [
            {
                "system": "http://loinc.org",
                "code": lab_result.loinc_code,
                "display": str(lab_result.test_name),
            }
        ]

    obs_id = f"OBS-{lab_result.pk}"
    resource = {
        "resourceType": "Observation",
        "id": obs_id,
        "status": "final",
        "subject": _ref("Patient", lab_result.encounter.patient.universal_id),
        "encounter": _ref("Encounter", f"ENC-{lab_result.encounter_id}"),
        "code": {
            "coding": coding,
            "text": str(lab_result.test_name),
        },
        "valueString": str(lab_result.result_value),
        "interpretation": [
            {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation",
                        "code": "A" if lab_result.is_abnormal else "N",
                        "display": "Abnormal" if lab_result.is_abnormal else "Normal",
                    }
                ]
            }
        ],
        "effectiveDateTime": _iso(lab_result.performed_at or lab_result.created_at),
        "issued": _iso(lab_result.created_at),
    }

    if lab_result.reference_range:
        resource["referenceRange"] = [{"text": lab_result.reference_range}]

    return resource


# ── $everything bundle ────────────────────────────────────────────────────


def patient_everything(patient, encounters_qs) -> dict:
    """
    Build a FHIR R4 Bundle (type=searchset) for GET /fhir/Patient/<nhid>/$everything.

    Includes: Patient, all Encounters, Conditions, MedicationRequests, Observations.
    """
    entries = []

    def _entry(resource):
        rt = resource["resourceType"]
        rid = resource["id"]
        entries.append(
            {
                "fullUrl": f"{_base_url()}/{rt}/{rid}",
                "resource": resource,
            }
        )

    # Patient
    _entry(patient_to_fhir(patient))

    for enc in encounters_qs:
        _entry(encounter_to_fhir(enc))
        for diag in enc.diagnoses.all():
            _entry(diagnosis_to_fhir(diag))
        for rx in enc.prescriptions.all():
            _entry(prescription_to_fhir(rx))
        for lab in enc.lab_results.all():
            _entry(lab_result_to_fhir(lab))

    return {
        "resourceType": "Bundle",
        "id": f"everything-{patient.universal_id}",
        "type": "searchset",
        "total": len(entries),
        "entry": entries,
    }
