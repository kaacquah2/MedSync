import json
import pytest
from rest_framework import status

from records.models import ConfidentialityLevel, Diagnosis, Encounter, PatientDocument


@pytest.mark.django_db
class TestConfidentialityTagging:
    """Test suite for ConfidentialityLevel schema & API serialization under Act 843 §37."""

    def test_model_defaults(self, patient_a, doctor_a):
        """Encounter, Diagnosis, and PatientDocument must default to NORMAL confidentiality."""
        encounter = Encounter.objects.create(
            patient=patient_a,
            encounter_type=Encounter.EncounterType.OUTPATIENT,
            chief_complaint="Routine checkup",
            created_by=doctor_a,
            created_at_hospital=doctor_a.hospital,
        )
        assert encounter.confidentiality == ConfidentialityLevel.NORMAL
        assert encounter.get_confidentiality_display() == "Normal (Standard Clinical Record)"

        diagnosis = Diagnosis.objects.create(
            encounter=encounter,
            description="Essential hypertension",
            created_by=doctor_a,
        )
        assert diagnosis.confidentiality == ConfidentialityLevel.NORMAL

    def test_create_restricted_encounter_api(self, client_as_doctor_a, patient_a):
        """Creating an encounter with confidentiality='restricted' stores and serializes correctly."""
        url = f"/api/patients/{patient_a.universal_id}/encounters/"
        payload = {
            "encounter_type": "OPD",
            "chief_complaint": "Psychotherapy & counseling session",
            "notes": "Patient discussed severe anxiety and depressive episodes.",
            "confidentiality": "restricted",
        }
        res = client_as_doctor_a.post(url, json.dumps(payload), content_type="application/json")
        assert res.status_code == status.HTTP_201_CREATED
        data = res.json()
        assert data["confidentiality"] == "restricted"
        assert "Restricted" in data["confidentiality_display"]

        # Verify in DB
        enc = Encounter.objects.get(pk=data["id"])
        assert enc.confidentiality == ConfidentialityLevel.RESTRICTED

    def test_invalid_confidentiality_falls_back_to_normal(self, client_as_doctor_a, patient_a):
        """Passing an invalid confidentiality string gracefully falls back to NORMAL."""
        url = f"/api/patients/{patient_a.universal_id}/encounters/"
        payload = {
            "encounter_type": "OPD",
            "chief_complaint": "General weakness",
            "confidentiality": "invalid_tier_xyz",
        }
        res = client_as_doctor_a.post(url, json.dumps(payload), content_type="application/json")
        assert res.status_code == status.HTTP_201_CREATED
        data = res.json()
        assert data["confidentiality"] == "normal"

    def test_create_restricted_diagnosis_api(self, client_as_doctor_a, encounter_a):
        """Doctor can attach a restricted diagnosis to an encounter."""
        url = f"/api/encounters/{encounter_a.pk}/diagnoses/"
        payload = {
            "description": "Major depressive disorder, recurrent, moderate",
            "icd_code": "F33.1",
            "is_primary": True,
            "confidentiality": "restricted",
        }
        res = client_as_doctor_a.post(url, json.dumps(payload), content_type="application/json")
        assert res.status_code == status.HTTP_201_CREATED
        data = res.json()
        assert data["confidentiality"] == "restricted"
        assert "Restricted" in data["confidentiality_display"]

        diag = Diagnosis.objects.get(pk=data["id"])
        assert diag.confidentiality == ConfidentialityLevel.RESTRICTED
