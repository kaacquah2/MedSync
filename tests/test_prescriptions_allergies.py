import json

import pytest

from audit.models import AuditLog
from patients.models import PatientAlert
from records.models import Prescription


@pytest.fixture
def penicillin_allergy(patient_a, hospital_a, doctor_a):
    return PatientAlert.objects.create(
        patient=patient_a,
        kind=PatientAlert.Kind.ALLERGY,
        label="Penicillin",
        severity=PatientAlert.Severity.SEVERE,
        reaction="Anaphylaxis and respiratory distress",
        recorded_by=doctor_a,
        recorded_at_hospital=hospital_a,
        is_active=True,
    )


class TestPrescriptionAllergyEnforcement:
    def test_prescribe_without_allergy_conflict_succeeds(self, client_as_doctor_a, encounter_a):
        resp = client_as_doctor_a.post(
            f"/api/encounters/{encounter_a.pk}/prescriptions/",
            json.dumps(
                {"drug_name": "Paracetamol 500mg", "dosage": "500mg oral", "frequency": "8h"}
            ),
            content_type="application/json",
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["drug_name"] == "Paracetamol 500mg"

    def test_penicillin_allergy_blocks_amoxicillin_without_override(
        self, client_as_doctor_a, encounter_a, penicillin_allergy
    ):
        resp = client_as_doctor_a.post(
            f"/api/encounters/{encounter_a.pk}/prescriptions/",
            json.dumps(
                {"drug_name": "Amoxicillin 500mg", "dosage": "500mg oral", "frequency": "8h"}
            ),
            content_type="application/json",
        )
        assert resp.status_code == 409
        body = resp.json()
        assert body["error"] == "ALLERGY_CONFLICT"
        assert "Penicillin" in body["detail"]
        assert len(body["conflicts"]) >= 1
        assert body["conflicts"][0]["allergy_label"] == "Penicillin"
        assert body["conflicts"][0]["severity"] == "SEVERE"
        # Ensure no prescription was saved
        assert not Prescription.objects.filter(encounter=encounter_a).exists()

    def test_insufficient_override_reason_rejected(
        self, client_as_doctor_a, encounter_a, penicillin_allergy
    ):
        # Shorter than 10 characters
        resp = client_as_doctor_a.post(
            f"/api/encounters/{encounter_a.pk}/prescriptions/",
            json.dumps(
                {
                    "drug_name": "Amoxicillin 500mg",
                    "dosage": "500mg oral",
                    "frequency": "8h",
                    "allergy_override_reason": "ok",
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 409
        assert resp.json()["error"] == "ALLERGY_CONFLICT"

    def test_valid_override_reason_allows_prescription_and_audits(
        self, client_as_doctor_a, encounter_a, penicillin_allergy
    ):
        override_text = "Desensitization completed under immunology supervision in ICU."
        resp = client_as_doctor_a.post(
            f"/api/encounters/{encounter_a.pk}/prescriptions/",
            json.dumps(
                {
                    "drug_name": "Amoxicillin 500mg",
                    "dosage": "500mg oral",
                    "frequency": "8h",
                    "allergy_override_reason": override_text,
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["drug_name"] == "Amoxicillin 500mg"
        assert data["allergy_override_reason"] == override_text

        # Verify database record
        rx = Prescription.objects.filter(encounter=encounter_a).first()
        assert rx is not None
        assert rx.drug_name == "Amoxicillin 500mg"
        assert rx.allergy_override_reason == override_text

        # Verify audit log recorded the clinical override in extra JSON
        audit = (
            AuditLog.objects.filter(
                action=AuditLog.Action.CREATE_PRESCRIPTION,
                patient_nhid=encounter_a.patient.nhid,
            )
            .order_by("-id")
            .first()
        )
        assert audit is not None
        assert audit.extra is not None
        assert audit.extra.get("allergy_override") is True
        assert audit.extra.get("override_reason") == override_text

    def test_inactive_allergy_does_not_block_prescription(
        self, client_as_doctor_a, encounter_a, penicillin_allergy
    ):
        penicillin_allergy.is_active = False
        penicillin_allergy.save()

        resp = client_as_doctor_a.post(
            f"/api/encounters/{encounter_a.pk}/prescriptions/",
            json.dumps(
                {"drug_name": "Amoxicillin 500mg", "dosage": "500mg oral", "frequency": "8h"}
            ),
            content_type="application/json",
        )
        assert resp.status_code == 201

    def test_sulfa_allergy_blocks_cotrimoxazole(
        self, client_as_doctor_a, encounter_a, hospital_a, doctor_a
    ):
        PatientAlert.objects.create(
            patient=encounter_a.patient,
            kind=PatientAlert.Kind.ALLERGY,
            label="Sulfa",
            severity=PatientAlert.Severity.MODERATE,
            reaction="Rash and hives",
            recorded_by=doctor_a,
            recorded_at_hospital=hospital_a,
            is_active=True,
        )

        resp = client_as_doctor_a.post(
            f"/api/encounters/{encounter_a.pk}/prescriptions/",
            json.dumps(
                {"drug_name": "Co-trimoxazole 480mg", "dosage": "480mg oral", "frequency": "12h"}
            ),
            content_type="application/json",
        )
        assert resp.status_code == 409
        assert resp.json()["error"] == "ALLERGY_CONFLICT"

    def test_nsaid_allergy_blocks_ibuprofen(
        self, client_as_doctor_a, encounter_a, hospital_a, doctor_a
    ):
        PatientAlert.objects.create(
            patient=encounter_a.patient,
            kind=PatientAlert.Kind.ALLERGY,
            label="Aspirin / NSAIDs",
            severity=PatientAlert.Severity.LIFE_THREAT,
            reaction="Bronchospasm and angioedema",
            recorded_by=doctor_a,
            recorded_at_hospital=hospital_a,
            is_active=True,
        )

        resp = client_as_doctor_a.post(
            f"/api/encounters/{encounter_a.pk}/prescriptions/",
            json.dumps({"drug_name": "Ibuprofen 400mg", "dosage": "400mg oral", "frequency": "8h"}),
            content_type="application/json",
        )
        assert resp.status_code == 409
        assert resp.json()["error"] == "ALLERGY_CONFLICT"
