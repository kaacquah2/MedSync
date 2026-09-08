"""
Tests for object-level authorization scoping across mutating API endpoints.

Verifies that cross-hospital actors receive 403 Forbidden when attempting to update:
1. Medication administration status (records.py)
2. Referral status (referrals_views.py)
3. Shift end status (shifts_views.py)
4. Handover acknowledgement (shifts_views.py)
5. Bed status (wards.py)
"""

import json

import pytest
from django.contrib.auth import get_user_model

from hospitals.models import Bed, Ward
from records.models import MedicationAdministration, Prescription
from referrals.models import Referral
from shifts.models import Handover, ShiftRecord

User = get_user_model()


def _make_user(username, role, hospital=None, password="Test@password1"):
    return User.objects.create_user(
        username=username,
        password=password,
        role=role,
        hospital=hospital,
        first_name=username.capitalize(),
        last_name="Demo",
        email=f"{username}@test.local",
    )


@pytest.fixture
def admin_a(db, hospital_a):
    return _make_user("admin_a", "hospital_admin", hospital_a)


@pytest.fixture
def admin_b(db, hospital_b):
    return _make_user("admin_b", "hospital_admin", hospital_b)


@pytest.fixture
def nurse_b(db, hospital_b):
    return _make_user("nurse_b", "nurse", hospital_b)


@pytest.fixture
def ward_a(db, hospital_a):
    return Ward.objects.create(hospital=hospital_a, name="Ward A", code="WA")


@pytest.fixture
def bed_a(db, ward_a):
    return Bed.objects.create(ward=ward_a, label="A1")


@pytest.fixture
def med_admin_a(db, encounter_a, doctor_a):
    rx = Prescription.objects.create(
        encounter=encounter_a,
        drug_name="Paracetamol",
        dosage="500mg",
        frequency="TDS",
        created_by=doctor_a,
    )
    return MedicationAdministration.objects.create(
        prescription=rx,
        scheduled_time="2026-08-10T10:00:00Z",
    )


@pytest.fixture
def referral_a_to_b(db, patient_a, hospital_a, hospital_b, doctor_a):
    return Referral.objects.create(
        patient=patient_a,
        from_hospital=hospital_a,
        to_hospital=hospital_b,
        from_provider=doctor_a,
        reason="Specialist consultation",
    )


@pytest.fixture
def shift_a(db, nurse_a, ward_a):
    return ShiftRecord.objects.create(user=nurse_a, ward=ward_a)


@pytest.fixture
def handover_a(db, shift_a, nurse_a, ward_a):
    return Handover.objects.create(
        shift=shift_a,
        from_user=nurse_a,
        to_user=None,
        ward=ward_a,
        summary="Patient stable",
    )


class TestAuthorizationScoping:
    def test_medication_admin_cross_hospital_denied(self, client, nurse_b, med_admin_a):
        client.force_login(nurse_b)
        resp = client.patch(
            f"/api/med-admins/{med_admin_a.pk}/status/",
            json.dumps({"status": "given"}),
            content_type="application/json",
        )
        assert resp.status_code == 403

    def test_referral_cross_hospital_denied(
        self, client, admin_a, patient_a, hospital_b, hospital_a
    ):
        from hospitals.models import Hospital

        hospital_c = Hospital.objects.create(name="Hospital C", code="HSPC", city="Tamale")
        doctor_c = _make_user("doctor_c", "doctor", hospital_c)

        unrelated_referral = Referral.objects.create(
            patient=patient_a,
            from_hospital=hospital_a,
            to_hospital=hospital_b,
            from_provider=admin_a,
            reason="Transfer",
        )

        client.force_login(doctor_c)
        resp = client.patch(
            f"/api/referrals/{unrelated_referral.pk}/status/",
            json.dumps({"status": "accepted"}),
            content_type="application/json",
        )
        assert resp.status_code == 403

    def test_shift_end_cross_hospital_admin_denied(self, client, admin_b, shift_a):
        client.force_login(admin_b)
        resp = client.patch(
            f"/api/shifts/{shift_a.pk}/end/",
            json.dumps({"break_minutes": 30}),
            content_type="application/json",
        )
        assert resp.status_code == 403

    def test_handover_acknowledge_cross_hospital_denied(self, client, nurse_b, handover_a):
        client.force_login(nurse_b)
        resp = client.patch(
            f"/api/handovers/{handover_a.pk}/acknowledge/",
            content_type="application/json",
        )
        assert resp.status_code == 403

    def test_bed_status_cross_hospital_admin_denied(self, client, admin_b, bed_a):
        client.force_login(admin_b)
        resp = client.patch(
            f"/api/beds/{bed_a.pk}/status/",
            json.dumps({"status": "cleaning"}),
            content_type="application/json",
        )
        assert resp.status_code == 403

    def test_ward_detail_cross_hospital_denied(self, client, admin_b, ward_a):
        client.force_login(admin_b)
        resp = client.get(f"/api/wards/{ward_a.pk}/")
        assert resp.status_code == 403
