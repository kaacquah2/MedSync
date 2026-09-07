"""
Tests for the FHIR R4 layer (fhir/mappers.py, fhir/views.py).

Verifies:
  - Full FHIR R4 schema validation via fhir.resources Pydantic models for Patient,
    Encounter, Condition, MedicationRequest, Observation, and Bundle.
  - Consistent resolvable resource references (Patient/NHID-*, Encounter/ENC-*,
    Condition/COND-*, MedicationRequest/MED-*, Observation/OBS-*, Organization/HOSP-*, Practitioner/PRAC-*).
  - Standard coding system URIs (ICD-10, SNOMED CT, LOINC, RxNorm, ActCode, etc.).
  - Read-only HTTP enforcement (POST/PUT/PATCH/DELETE return 405 Method Not Allowed).
  - RBAC & break-glass access control (clinical/admin role enforcement and inter-hospital break-glass grants).
"""

from datetime import timedelta

import pytest
from django.utils import timezone
from fhir.resources.R4B.bundle import Bundle
from fhir.resources.R4B.condition import Condition as FHIRCondition
from fhir.resources.R4B.encounter import Encounter as FHIREncounter
from fhir.resources.R4B.medicationrequest import MedicationRequest as FHIRMedicationRequest
from fhir.resources.R4B.observation import Observation as FHIRObservation
from fhir.resources.R4B.patient import Patient as FHIRPatient

from access.models import BreakGlassAccess

# ── Helper fixture for a rich clinical record ─────────────────────────────────


@pytest.fixture
def clinical_encounter(db, patient_a, doctor_a, hospital_a):
    from records.models import Diagnosis, Encounter, LabResult, Prescription

    enc = Encounter.objects.create(
        patient=patient_a,
        encounter_type="OPD",
        chief_complaint="High fever and muscle pain",
        created_by=doctor_a,
        created_at_hospital=hospital_a,
    )
    diag = Diagnosis.objects.create(
        encounter=enc,
        description="Malaria infection",
        icd_code="B54",
        snomed_code="61462000",
        created_by=doctor_a,
    )
    rx = Prescription.objects.create(
        encounter=enc,
        drug_name="Artemether-Lumefantrine",
        dosage="80/480 mg",
        frequency="Twice daily for 3 days",
        rxnorm_code="284635",
        instructions="Take after meals",
        created_by=doctor_a,
    )
    lab = LabResult.objects.create(
        encounter=enc,
        test_name="Malaria Blood Smear",
        result_value="Positive (2+ ring forms)",
        loinc_code="34568-6",
        is_abnormal=True,
        performed_at=timezone.now(),
        created_by=doctor_a,
    )
    return enc, diag, rx, lab


# ── 1. Schema Validation Unit Tests ───────────────────────────────────────────


class TestFhirSchemaValidation:
    def test_patient_to_fhir_schema_valid(self, db, patient_a):
        from fhir.mappers import patient_to_fhir

        res = patient_to_fhir(patient_a)
        fhir_patient = FHIRPatient(**res)
        assert fhir_patient.get_resource_type() == "Patient"
        assert fhir_patient.id == patient_a.universal_id

    def test_encounter_to_fhir_schema_valid(self, db, clinical_encounter):
        enc, _, _, _ = clinical_encounter
        from fhir.mappers import encounter_to_fhir

        res = encounter_to_fhir(enc)
        fhir_enc = FHIREncounter(**res)
        assert fhir_enc.get_resource_type() == "Encounter"

    def test_diagnosis_to_fhir_schema_valid(self, db, clinical_encounter):
        _, diag, _, _ = clinical_encounter
        from fhir.mappers import diagnosis_to_fhir

        res = diagnosis_to_fhir(diag)
        fhir_cond = FHIRCondition(**res)
        assert fhir_cond.get_resource_type() == "Condition"

    def test_prescription_to_fhir_schema_valid(self, db, clinical_encounter):
        _, _, rx, _ = clinical_encounter
        from fhir.mappers import prescription_to_fhir

        res = prescription_to_fhir(rx)
        fhir_rx = FHIRMedicationRequest(**res)
        assert fhir_rx.get_resource_type() == "MedicationRequest"

    def test_lab_result_to_fhir_schema_valid(self, db, clinical_encounter):
        _, _, _, lab = clinical_encounter
        from fhir.mappers import lab_result_to_fhir

        res = lab_result_to_fhir(lab)
        fhir_obs = FHIRObservation(**res)
        assert fhir_obs.get_resource_type() == "Observation"

    def test_patient_everything_bundle_schema_valid(self, db, patient_a, clinical_encounter):
        from fhir.mappers import patient_everything
        from records.models import Encounter

        qs = Encounter.objects.filter(patient=patient_a).prefetch_related(
            "diagnoses", "prescriptions", "lab_results"
        )
        bundle_dict = patient_everything(patient_a, qs)

        # Validate complete Bundle schema using fhir.resources.R4B
        fhir_bundle = Bundle(**bundle_dict)
        assert fhir_bundle.get_resource_type() == "Bundle"
        assert fhir_bundle.type == "searchset"
        assert (
            len(fhir_bundle.entry) == 5
        )  # Patient + Encounter + Condition + MedicationRequest + Observation


# ── 2. Resource Reference Consistency & Format Tests ─────────────────────────


class TestResourceReferences:
    def test_prefixed_resolvable_ids(self, db, patient_a, clinical_encounter):
        enc, diag, rx, lab = clinical_encounter
        from fhir.mappers import (
            diagnosis_to_fhir,
            encounter_to_fhir,
            lab_result_to_fhir,
            patient_to_fhir,
            prescription_to_fhir,
        )

        p_res = patient_to_fhir(patient_a)
        enc_res = encounter_to_fhir(enc)
        diag_res = diagnosis_to_fhir(diag)
        rx_res = prescription_to_fhir(rx)
        lab_res = lab_result_to_fhir(lab)

        # Resource IDs
        assert p_res["id"] == patient_a.universal_id
        assert enc_res["id"] == f"ENC-{enc.pk}"
        assert diag_res["id"] == f"COND-{diag.pk}"
        assert rx_res["id"] == f"MED-{rx.pk}"
        assert lab_res["id"] == f"OBS-{lab.pk}"

        # Child resource references match parent resource IDs
        expected_patient_ref = f"Patient/{patient_a.universal_id}"
        expected_enc_ref = f"Encounter/ENC-{enc.pk}"

        assert enc_res["subject"]["reference"] == expected_patient_ref
        assert diag_res["subject"]["reference"] == expected_patient_ref
        assert diag_res["encounter"]["reference"] == expected_enc_ref

        assert rx_res["subject"]["reference"] == expected_patient_ref
        assert rx_res["encounter"]["reference"] == expected_enc_ref

        assert lab_res["subject"]["reference"] == expected_patient_ref
        assert lab_res["encounter"]["reference"] == expected_enc_ref

        # Organization and Practitioner references
        assert (
            p_res["managingOrganization"]["reference"]
            == f"Organization/HOSP-{patient_a.registered_at_hospital_id}"
        )
        assert (
            enc_res["serviceProvider"]["reference"]
            == f"Organization/HOSP-{enc.created_at_hospital_id}"
        )
        assert (
            enc_res["participant"][0]["individual"]["reference"]
            == f"Practitioner/PRAC-{enc.created_by_id}"
        )
        assert diag_res["recorder"]["reference"] == f"Practitioner/PRAC-{diag.created_by_id}"
        assert rx_res["requester"]["reference"] == f"Practitioner/PRAC-{rx.created_by_id}"


# ── 3. Coding System URI Tests ───────────────────────────────────────────────


class TestCodingSystemURIs:
    def test_standard_coding_uris(self, db, clinical_encounter):
        enc, diag, rx, lab = clinical_encounter
        from fhir.mappers import (
            diagnosis_to_fhir,
            encounter_to_fhir,
            lab_result_to_fhir,
            prescription_to_fhir,
        )

        enc_res = encounter_to_fhir(enc)
        diag_res = diagnosis_to_fhir(diag)
        rx_res = prescription_to_fhir(rx)
        lab_res = lab_result_to_fhir(lab)

        # Encounter class system
        assert enc_res["class"]["system"] == "http://terminology.hl7.org/CodeSystem/v3-ActCode"

        # Diagnosis ICD-10 and SNOMED URIs
        diag_codings = diag_res["code"]["coding"]
        icd_coding = next(c for c in diag_codings if c["code"] == diag.icd_code)
        snomed_coding = next(c for c in diag_codings if c["code"] == diag.snomed_code)
        assert icd_coding["system"] == "http://hl7.org/fhir/sid/icd-10"
        assert snomed_coding["system"] == "http://snomed.info/sct"

        # Prescription RxNorm URI
        rx_coding = rx_res["medicationCodeableConcept"]["coding"][0]
        assert rx_coding["system"] == "http://www.nlm.nih.gov/research/umls/rxnorm"
        assert rx_coding["code"] == rx.rxnorm_code

        # LabResult LOINC URI
        lab_coding = lab_res["code"]["coding"][0]
        assert lab_coding["system"] == "http://loinc.org"
        assert lab_coding["code"] == lab.loinc_code


# ── 4. Read-Only Enforcement Tests ────────────────────────────────────────────


class TestFhirReadOnlyEnforcement:
    def test_patient_endpoint_http_methods(self, db, client, doctor_a, patient_a):
        client.force_login(doctor_a)
        url = f"/fhir/Patient/{patient_a.universal_id}/"

        assert client.get(url).status_code == 200
        assert client.post(url, data={}).status_code == 405
        assert client.put(url, data={}).status_code == 405
        assert client.patch(url, data={}).status_code == 405
        assert client.delete(url).status_code == 405

    def test_everything_endpoint_http_methods(self, db, client, doctor_a, patient_a):
        client.force_login(doctor_a)
        url = f"/fhir/Patient/{patient_a.universal_id}/$everything"

        assert client.get(url).status_code == 200
        assert client.post(url, data={}).status_code == 405
        assert client.put(url, data={}).status_code == 405
        assert client.patch(url, data={}).status_code == 405
        assert client.delete(url).status_code == 405


# ── 5. Access Control & RBAC / Break-Glass Tests ──────────────────────────────


class TestFhirAccessControl:
    def test_anonymous_redirected(self, client, patient_a):
        resp = client.get(f"/fhir/Patient/{patient_a.universal_id}/")
        assert resp.status_code == 302

    def test_receptionist_denied_403(self, db, client, receptionist_a, patient_a):
        """Receptionists have non-clinical role and must be denied access."""
        client.force_login(receptionist_a)
        resp = client.get(f"/fhir/Patient/{patient_a.universal_id}/")
        assert resp.status_code == 403
        data = resp.json()
        assert data["resourceType"] == "OperationOutcome"
        assert "Role not authorized" in data["issue"][0]["diagnostics"]

    def test_doctor_same_hospital_granted_200(self, db, client, doctor_a, patient_a):
        client.force_login(doctor_a)
        resp = client.get(f"/fhir/Patient/{patient_a.universal_id}/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["resourceType"] == "Patient"

    def test_doctor_cross_hospital_denied_403(self, db, client, doctor_b, patient_a):
        """doctor_b at Hospital B cannot access patient_a at Hospital A without break-glass."""
        client.force_login(doctor_b)
        resp = client.get(f"/fhir/Patient/{patient_a.universal_id}/")
        assert resp.status_code == 403
        data = resp.json()
        assert data["resourceType"] == "OperationOutcome"
        assert "Insufficient access" in data["issue"][0]["diagnostics"]

    def test_doctor_cross_hospital_with_break_glass_granted_200(
        self, db, client, doctor_b, patient_a
    ):
        """doctor_b with active break-glass grant is permitted cross-hospital FHIR access."""
        BreakGlassAccess.objects.create(
            actor=doctor_b,
            patient=patient_a,
            reason="Emergency trauma evaluation",
            expires_at=timezone.now() + timedelta(hours=1),
        )
        client.force_login(doctor_b)
        resp = client.get(f"/fhir/Patient/{patient_a.universal_id}/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["resourceType"] == "Patient"

        # $everything bundle also accessible under break-glass
        resp_everything = client.get(f"/fhir/Patient/{patient_a.universal_id}/$everything")
        assert resp_everything.status_code == 200
        data_everything = resp_everything.json()
        assert data_everything["resourceType"] == "Bundle"

    def test_super_admin_granted_200(self, db, client, sys_admin, patient_a):
        client.force_login(sys_admin)
        resp = client.get(f"/fhir/Patient/{patient_a.universal_id}/")
        assert resp.status_code == 200

    def test_404_unknown_patient(self, db, client, doctor_a):
        client.force_login(doctor_a)
        resp = client.get("/fhir/Patient/NHID-XXXXXXXX/")
        assert resp.status_code == 404


# ── 6. CapabilityStatement Metadata Endpoint Tests ─────────────────────────────


class TestFhirCapabilityStatement:
    def test_unauthenticated_metadata_returns_capability_statement(self, client):
        resp = client.get("/fhir/metadata")
        assert resp.status_code == 200
        assert resp["Content-Type"] == "application/fhir+json"

        data = resp.json()
        assert data["resourceType"] == "CapabilityStatement"
        assert data["status"] == "active"
        assert data["fhirVersion"] == "4.0.1"
        assert len(data["rest"]) > 0
        resources = data["rest"][0]["resource"]
        patient_res = next(r for r in resources if r["type"] == "Patient")
        assert patient_res["interaction"][0]["code"] == "read"
