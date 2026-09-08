"""
Tests for the Patient model and API views.

Verifies:
  - NHID auto-generation and uniqueness
  - Encrypted fields store ciphertext in DB
  - Blind-index populated on save, enables exact lookup
  - Patient search finds by NHID (fast path) and name via /api/patients/?q=
  - Cross-hospital patient lookup succeeds for any authenticated user
"""

from unittest.mock import patch
from django.db import IntegrityError
import pytest

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
        assert len(p.universal_id) == 21  # "NHID-" (5) + 16 hex chars

    def test_nhid_unique(self, db):
        ids = {generate_nhid() for _ in range(100)}
        assert len(ids) == 100  # no collisions in 100 attempts

    def test_two_patients_different_nhid(self, db, patient_a, patient_b):
        assert patient_a.universal_id != patient_b.universal_id

    def test_nhid_collision_retry(self, db):
        p1 = Patient.objects.create(
            first_name="Patient",
            last_name="One",
            date_of_birth="1990-01-01",
        )
        collided_id = p1.universal_id

        with patch("patients.models.generate_nhid", wraps=generate_nhid) as spy_generate:
            p2 = Patient(
                first_name="Patient",
                last_name="Two",
                date_of_birth="1995-05-05",
                universal_id=collided_id,
            )
            # Initially p2 has collided_id, save() will catch the collision and regenerate
            p2.save()

            assert p2.universal_id != collided_id
            assert p2.universal_id.startswith("NHID-")
            assert len(p2.universal_id) == 21
            assert spy_generate.call_count >= 1

    def test_nhid_collision_exhaustion_raises_integrity_error(self, db):
        p1 = Patient.objects.create(
            first_name="Patient",
            last_name="One",
            date_of_birth="1990-01-01",
        )
        collided_id = p1.universal_id

        with patch("patients.models.generate_nhid", return_value=collided_id):
            p2 = Patient(
                first_name="Patient",
                last_name="Two",
                date_of_birth="1995-05-05",
                universal_id=collided_id,
            )
            with pytest.raises(IntegrityError):
                p2.save()

    def test_existing_patient_update_does_not_change_nhid(self, db, patient_a):
        original_id = patient_a.universal_id
        patient_a.first_name = "UpdatedName"
        patient_a.save()
        patient_a.refresh_from_db()
        assert patient_a.universal_id == original_id



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
        match = next(p for p in results if p["universal_id"] == patient_a.universal_id)
        assert match["has_access"] is True
        assert match["first_name"] == "Yaw"
        assert match["last_name"] == "Mensah"
        assert match["full_name"] == "Yaw Mensah"

    def test_search_by_name(self, client_as_doctor_a, patient_a):
        resp = client_as_doctor_a.get("/api/patients/?q=Yaw")
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert any(p["universal_id"] == patient_a.universal_id for p in results)

    def test_search_by_nonexistent_nhid(self, client_as_doctor_a, patient_a):
        """Searching for a mistyped or nonexistent NHID returns 200 without NameError or 500."""
        resp = client_as_doctor_a.get("/api/patients/?q=NHID-NONEXISTENT")
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert not any(p["universal_id"] == patient_a.universal_id for p in results)

    def test_search_requires_login(self, client):
        resp = client.get("/api/patients/?q=test")
        assert resp.status_code == 401

    def test_cross_hospital_patient_visible_to_other_hospital(self, client_as_doctor_b, patient_a):
        """Doctor at Hospital B can find a patient registered at Hospital A, but receives only a stub."""
        resp = client_as_doctor_b.get(f"/api/patients/?q={patient_a.universal_id}")
        assert resp.status_code == 200
        results = resp.json()["results"]
        match = next(p for p in results if p["universal_id"] == patient_a.universal_id)
        assert match["has_access"] is False
        assert match["first_name"] is None
        assert match["last_name"] is None
        assert match["full_name"] is None
        assert match["date_of_birth"] is None
        assert match["sex"] is None
        assert match["blood_group"] is None
        assert match["registered_at_hospital"]["name"] == patient_a.registered_at_hospital.name

    def test_cross_hospital_national_id_search_returns_stub(self, client_as_doctor_b, patient_a):
        """Presenting Ghana Card (National ID) matches nationwide as a stub to prevent duplicate registrations."""
        resp = client_as_doctor_b.get(f"/api/patients/?q={patient_a.national_id}")
        assert resp.status_code == 200
        results = resp.json()["results"]
        match = next(p for p in results if p["universal_id"] == patient_a.universal_id)
        assert match["has_access"] is False
        assert match["first_name"] is None
        assert match["last_name"] is None
        assert match["full_name"] is None

    def test_cross_hospital_name_search_does_not_leak(self, client_as_doctor_b, patient_a):
        """Doctor B searching by name cannot find Patient A at Hospital A (prevents national name enumeration)."""
        resp = client_as_doctor_b.get("/api/patients/?q=Yaw")
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert not any(p["universal_id"] == patient_a.universal_id for p in results)


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

    def test_get_patient_returns_etag_header(self, client_as_doctor_a, patient_a):
        resp = client_as_doctor_a.get(f"/api/patients/{patient_a.universal_id}/")
        assert resp.status_code == 200
        assert "ETag" in resp.headers
        assert resp.headers["ETag"].strip('"') == patient_a.updated_at.isoformat()

    def test_patch_patient_without_concurrency_token_succeeds(self, client_as_doctor_a, patient_a):
        resp = client_as_doctor_a.patch(
            f"/api/patients/{patient_a.universal_id}/",
            {"phone": "+233200000001"},
            content_type="application/json",
        )
        assert resp.status_code == 200
        patient_a.refresh_from_db()
        assert patient_a.phone == "+233200000001"

    def test_patch_patient_with_matching_updated_at_succeeds(self, client_as_doctor_a, patient_a):
        current_updated = patient_a.updated_at.isoformat()
        resp = client_as_doctor_a.patch(
            f"/api/patients/{patient_a.universal_id}/",
            {
                "phone": "+233200000002",
                "updated_at": current_updated,
            },
            content_type="application/json",
        )
        assert resp.status_code == 200
        patient_a.refresh_from_db()
        assert patient_a.phone == "+233200000002"

    def test_patch_patient_with_matching_if_match_header_succeeds(self, client_as_doctor_a, patient_a):
        current_updated = patient_a.updated_at.isoformat()
        resp = client_as_doctor_a.patch(
            f"/api/patients/{patient_a.universal_id}/",
            {"phone": "+233200000003"},
            content_type="application/json",
            HTTP_IF_MATCH=f'"{current_updated}"',
        )
        assert resp.status_code == 200
        patient_a.refresh_from_db()
        assert patient_a.phone == "+233200000003"

    def test_patch_patient_with_stale_updated_at_returns_409_conflict(self, client_as_doctor_a, patient_a):
        stale_updated = "2020-01-01T00:00:00Z"
        resp = client_as_doctor_a.patch(
            f"/api/patients/{patient_a.universal_id}/",
            {
                "phone": "+233200000099",
                "updated_at": stale_updated,
            },
            content_type="application/json",
        )
        assert resp.status_code == 409
        data = resp.json()
        assert data.get("code") == "CONCURRENCY_CONFLICT"
        assert "modified by another user" in data.get("error")
        # Verify no change persisted
        patient_a.refresh_from_db()
        assert patient_a.phone != "+233200000099"

    def test_patch_patient_with_stale_if_match_returns_409_conflict(self, client_as_doctor_a, patient_a):
        resp = client_as_doctor_a.patch(
            f"/api/patients/{patient_a.universal_id}/",
            {"phone": "+233200000099"},
            content_type="application/json",
            HTTP_IF_MATCH='"2020-01-01T00:00:00Z"',
        )
        assert resp.status_code == 409
        assert resp.json().get("code") == "CONCURRENCY_CONFLICT"
        patient_a.refresh_from_db()
        assert patient_a.phone != "+233200000099"
