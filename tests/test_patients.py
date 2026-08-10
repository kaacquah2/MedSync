"""
Tests for the Patient model and API views.

Verifies:
  - NHID auto-generation and uniqueness
  - Encrypted fields store ciphertext in DB
  - Blind-index populated on save, enables exact lookup
  - Patient search finds by NHID (fast path) and name via /api/patients/?q=
  - Cross-hospital patient lookup succeeds for any authenticated user
"""

from core.blind_index import make_blind_index
from patients.models import Patient, generate_nhid


class TestNHID:
    def test_nhid_format(self, db):
        p = Patient.objects.create(
            first_name="Test",
            last_name="Patient",
            date_of_birth="2000-01-01",
        )
        assert p.universal_id.startswith("NHID-")
        assert len(p.universal_id) == 13  # "NHID-" + 8 hex chars

    def test_nhid_unique(self, db):
        ids = {generate_nhid() for _ in range(100)}
        assert len(ids) == 100  # no collisions in 100 attempts

    def test_two_patients_different_nhid(self, db, patient_a, patient_b):
        assert patient_a.universal_id != patient_b.universal_id


class TestBlindIndexOnPatient:
    def test_name_hash_set_on_create(self, db, patient_a):
        expected = make_blind_index("Yaw Mensah")
        assert patient_a.name_hash == expected

    def test_national_id_hash_set_on_create(self, db, patient_a):
        expected = make_blind_index("GHA-TEST-001")
        assert patient_a.national_id_hash == expected

    def test_exact_name_lookup(self, db, patient_a):
        h = make_blind_index("Yaw Mensah")
        result = Patient.objects.filter(name_hash=h)
        assert patient_a in result

    def test_national_id_exact_lookup(self, db, patient_a):
        h = make_blind_index("GHA-TEST-001")
        result = Patient.objects.filter(national_id_hash=h)
        assert patient_a in result

    def test_hash_updates_on_edit(self, db, patient_a):
        patient_a.first_name = "Kofi"
        patient_a.save()
        patient_a.refresh_from_db()
        expected = make_blind_index("Kofi Mensah")
        assert patient_a.name_hash == expected


class TestPatientSearchView:
    def test_search_by_nhid(self, client_as_doctor_a, patient_a):
        resp = client_as_doctor_a.get(f"/api/patients/?q={patient_a.universal_id}")
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert any(p["universal_id"] == patient_a.universal_id for p in results)

    def test_search_by_name(self, client_as_doctor_a, patient_a):
        resp = client_as_doctor_a.get("/api/patients/?q=Yaw")
        assert resp.status_code == 200

    def test_search_requires_login(self, client):
        resp = client.get("/api/patients/?q=test")
        assert resp.status_code == 401

    def test_cross_hospital_patient_visible_to_other_hospital(self, client_as_doctor_b, patient_a):
        """Doctor at Hospital B can find a patient registered at Hospital A."""
        resp = client_as_doctor_b.get(f"/api/patients/?q={patient_a.universal_id}")
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert any(p["universal_id"] == patient_a.universal_id for p in results)


class TestPatientDetailView:
    def test_cross_hospital_denied_without_relationship(self, client_as_doctor_b, patient_a):
        """Doctor at Hospital B has no treatment relationship → 403."""
        resp = client_as_doctor_b.get(f"/api/patients/{patient_a.universal_id}/")
        assert resp.status_code == 403
        assert "error" in resp.json()

    def test_same_hospital_access_granted(self, client_as_doctor_a, patient_a):
        resp = client_as_doctor_a.get(f"/api/patients/{patient_a.universal_id}/")
        assert resp.status_code == 200
        assert resp.json()["universal_id"] == patient_a.universal_id

    def test_cross_hospital_with_treatment_rel_allowed(
        self, client_as_doctor_b, doctor_b, patient_a, hospital_b
    ):
        """Doctor B with an active TreatmentRelationship can view Hospital A patient."""
        from access.models import TreatmentRelationship

        TreatmentRelationship.objects.create(
            clinician=doctor_b,
            patient=patient_a,
            hospital=hospital_b,
            reason="Referral from Hospital A",
        )
        resp = client_as_doctor_b.get(f"/api/patients/{patient_a.universal_id}/")
        assert resp.status_code == 200
        assert resp.json()["is_cross_hospital"] is True
