"""
Tests for Phase B endpoints: appointments, referrals, shifts, vitals,
lab orders, and the staff reset-password endpoint.
"""

import json
from datetime import UTC, datetime, timedelta

import pytest

from audit.models import AuditLog

# ── Helper ────────────────────────────────────────────────────────────────────


def _make_user(username, role, hospital=None, password="Test@password1"):
    from accounts.models import User

    return User.objects.create_user(
        username=username,
        password=password,
        role=role,
        hospital=hospital,
        first_name=username.capitalize(),
        last_name="Test",
        email=f"{username}@test.local",
    )


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def nurse_b(db, hospital_b):
    return _make_user("nurse_b_pb", "nurse", hospital_b)


@pytest.fixture
def lab_tech_a(db, hospital_a):
    return _make_user("labtech_a_pb", "lab_technician", hospital_a)


@pytest.fixture
def hosp_admin_a(db, hospital_a):
    return _make_user("hadmin_a_pb", "hospital_admin", hospital_a)


@pytest.fixture
def target_staff_a(db, hospital_a):
    return _make_user("target_staff_pb", "nurse", hospital_a)


@pytest.fixture
def scheduled_dt():
    return (datetime.now(tz=UTC) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")


# ══════════════════════════════════════════════════════════════════════════════
# Appointments
# ══════════════════════════════════════════════════════════════════════════════


class TestAppointments:
    def test_doctor_can_create_appointment(
        self, db, client, doctor_a, patient_a, hospital_a, scheduled_dt
    ):
        client.force_login(doctor_a)
        resp = client.post(
            "/api/appointments/",
            json.dumps(
                {
                    "patient": patient_a.pk,
                    "hospital": hospital_a.pk,
                    "scheduled_for": scheduled_dt,
                    "appointment_type": "outpatient",
                    "reason": "Follow-up visit",
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["patient_nhid"] == patient_a.universal_id

    def test_create_appointment_creates_audit_row(
        self, db, client, doctor_a, patient_a, hospital_a, scheduled_dt
    ):
        client.force_login(doctor_a)
        client.post(
            "/api/appointments/",
            json.dumps(
                {
                    "patient": patient_a.pk,
                    "hospital": hospital_a.pk,
                    "scheduled_for": scheduled_dt,
                    "appointment_type": "outpatient",
                }
            ),
            content_type="application/json",
        )
        assert AuditLog.objects.filter(action="CREATE_APPOINTMENT").exists()

    def test_lab_technician_cannot_create_appointment(
        self, db, client, lab_tech_a, patient_a, hospital_a, scheduled_dt
    ):
        client.force_login(lab_tech_a)
        resp = client.post(
            "/api/appointments/",
            json.dumps(
                {
                    "patient": patient_a.pk,
                    "hospital": hospital_a.pk,
                    "scheduled_for": scheduled_dt,
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 403

    def test_status_transition_check_in(
        self, db, client, doctor_a, patient_a, hospital_a, scheduled_dt
    ):
        from scheduling.models import Appointment

        appt = Appointment.objects.create(
            patient=patient_a,
            hospital=hospital_a,
            created_by=doctor_a,
            scheduled_for=datetime.now(tz=UTC) + timedelta(hours=2),
            status="scheduled",
        )
        client.force_login(doctor_a)
        resp = client.post(
            f"/api/appointments/{appt.pk}/status/",
            json.dumps({"action": "check_in"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "checked_in"

    def test_invalid_status_transition_rejected(self, db, client, doctor_a, patient_a, hospital_a):
        from scheduling.models import Appointment

        appt = Appointment.objects.create(
            patient=patient_a,
            hospital=hospital_a,
            created_by=doctor_a,
            scheduled_for=datetime.now(tz=UTC) + timedelta(hours=1),
            status="completed",
        )
        client.force_login(doctor_a)
        resp = client.post(
            f"/api/appointments/{appt.pk}/status/",
            json.dumps({"action": "check_in"}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_cross_hospital_appointment_403(
        self, db, client, doctor_b, patient_a, hospital_a, doctor_a
    ):
        from scheduling.models import Appointment

        appt = Appointment.objects.create(
            patient=patient_a,
            hospital=hospital_a,
            created_by=doctor_a,
            scheduled_for=datetime.now(tz=UTC) + timedelta(hours=1),
        )
        client.force_login(doctor_b)
        resp = client.post(
            f"/api/appointments/{appt.pk}/status/",
            json.dumps({"action": "check_in"}),
            content_type="application/json",
        )
        assert resp.status_code == 403

    def test_list_scoped_by_hospital(self, db, client, doctor_a, hospital_a, patient_a):
        client.force_login(doctor_a)
        resp = client.get("/api/appointments/")
        assert resp.status_code == 200


# ══════════════════════════════════════════════════════════════════════════════
# Referrals
# ══════════════════════════════════════════════════════════════════════════════


class TestReferrals:
    def test_doctor_can_create_referral(
        self, db, client, doctor_a, patient_a, hospital_a, hospital_b
    ):
        # The serializer requires patient + from_hospital as FK PKs.
        # The view overrides from_hospital via save() but validation runs first.
        client.force_login(doctor_a)
        resp = client.post(
            "/api/referrals/",
            json.dumps(
                {
                    "patient": patient_a.pk,
                    "from_hospital": hospital_a.pk,
                    "to_hospital": hospital_b.pk,
                    "reason": "Specialist evaluation",
                    "priority": "routine",
                    "status": "sent",
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["patient_nhid"] == patient_a.universal_id
        assert data["from_hospital_name"] == hospital_a.name

    def test_create_referral_creates_audit_row(
        self, db, client, doctor_a, patient_a, hospital_a, hospital_b
    ):
        client.force_login(doctor_a)
        client.post(
            "/api/referrals/",
            json.dumps(
                {
                    "patient": patient_a.pk,
                    "from_hospital": hospital_a.pk,
                    "to_hospital": hospital_b.pk,
                    "reason": "Needs specialist",
                    "priority": "routine",
                    "status": "sent",
                }
            ),
            content_type="application/json",
        )
        assert AuditLog.objects.filter(action="CREATE_REFERRAL").exists()

    def test_status_update(self, db, client, doctor_b, patient_a, hospital_a, hospital_b, doctor_a):
        from referrals.models import Referral

        referral = Referral.objects.create(
            patient=patient_a,
            from_hospital=hospital_a,
            to_hospital=hospital_b,
            from_provider=doctor_a,
            reason="Back pain",
            priority="routine",
            status="sent",
        )
        client.force_login(doctor_b)
        resp = client.patch(
            f"/api/referrals/{referral.pk}/status/",
            json.dumps({"status": "accepted", "status_notes": "Will see patient"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"

    def test_invalid_status_rejected(self, db, client, doctor_a, patient_a, hospital_a, hospital_b):
        from referrals.models import Referral

        referral = Referral.objects.create(
            patient=patient_a,
            from_hospital=hospital_a,
            to_hospital=hospital_b,
            from_provider=doctor_a,
            reason="Chest pain",
            priority="urgent",
            status="sent",
        )
        client.force_login(doctor_a)
        resp = client.patch(
            f"/api/referrals/{referral.pk}/status/",
            json.dumps({"status": "NOT_VALID"}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_receptionist_cannot_create_referral(
        self, db, client, hospital_a, patient_a, hospital_b
    ):
        recept = _make_user("recept_ref_pb", "receptionist", hospital_a)
        client.force_login(recept)
        resp = client.post(
            "/api/referrals/",
            json.dumps(
                {
                    "patient_nhid": patient_a.universal_id,
                    "to_hospital": hospital_b.pk,
                    "reason": "Test",
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 403

    def test_hospital_admin_cannot_create_referral(
        self, db, client, hospital_a, patient_a, hospital_b
    ):
        hosp_admin = _make_user("admin_ref_pb", "hospital_admin", hospital_a)
        client.force_login(hosp_admin)
        resp = client.post(
            "/api/referrals/",
            json.dumps(
                {
                    "patient": patient_a.pk,
                    "from_hospital": hospital_a.pk,
                    "to_hospital": hospital_b.pk,
                    "reason": "Test admin",
                    "priority": "routine",
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 403

    def test_hospital_admin_cannot_update_referral_status(
        self, db, client, hospital_a, patient_a, hospital_b, doctor_a
    ):
        from referrals.models import Referral

        referral = Referral.objects.create(
            patient=patient_a,
            from_hospital=hospital_a,
            to_hospital=hospital_b,
            from_provider=doctor_a,
            reason="Cardiology review",
            priority="routine",
            status="sent",
        )
        hosp_admin = _make_user("admin_ref_status", "hospital_admin", hospital_b)
        client.force_login(hosp_admin)
        resp = client.patch(
            f"/api/referrals/{referral.pk}/status/",
            json.dumps({"status": "accepted", "status_notes": "Admin cannot approve"}),
            content_type="application/json",
        )
        assert resp.status_code == 403

    def test_hospital_admin_can_view_referrals(self, db, client, hospital_a):
        hosp_admin = _make_user("admin_ref_view", "hospital_admin", hospital_a)
        client.force_login(hosp_admin)
        resp = client.get("/api/referrals/")
        assert resp.status_code == 200


# ══════════════════════════════════════════════════════════════════════════════
# Shifts
# ══════════════════════════════════════════════════════════════════════════════


class TestShifts:
    def test_nurse_can_start_shift(self, db, client, nurse_a):
        client.force_login(nurse_a)
        resp = client.post(
            "/api/shifts/start/",
            json.dumps({}),
            content_type="application/json",
        )
        assert resp.status_code == 201
        assert resp.json()["is_active"] is True

    def test_start_shift_creates_audit_row(self, db, client, nurse_a):
        client.force_login(nurse_a)
        client.post("/api/shifts/start/", json.dumps({}), content_type="application/json")
        assert AuditLog.objects.filter(action="START_SHIFT").exists()

    def test_double_start_rejected(self, db, client, nurse_a):
        client.force_login(nurse_a)
        client.post("/api/shifts/start/", json.dumps({}), content_type="application/json")
        resp = client.post(
            "/api/shifts/start/",
            json.dumps({}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_nurse_can_end_own_shift(self, db, client, nurse_a):
        from shifts.models import ShiftRecord

        shift = ShiftRecord.objects.create(user=nurse_a)
        client.force_login(nurse_a)
        resp = client.patch(
            f"/api/shifts/{shift.pk}/end/",
            json.dumps({"break_minutes": 15}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

    def test_nurse_cannot_end_others_shift(self, db, client, nurse_a, nurse_b):
        from shifts.models import ShiftRecord

        shift = ShiftRecord.objects.create(user=nurse_b)
        client.force_login(nurse_a)
        resp = client.patch(
            f"/api/shifts/{shift.pk}/end/",
            json.dumps({}),
            content_type="application/json",
        )
        assert resp.status_code == 403

    def test_end_already_ended_shift_rejected(self, db, client, nurse_a):
        from datetime import timedelta

        from django.utils import timezone

        from shifts.models import ShiftRecord

        now = timezone.now()
        shift = ShiftRecord.objects.create(
            user=nurse_a,
            started_at=now - timedelta(hours=8),
            ended_at=now - timedelta(hours=1),  # ended_at > started_at satisfies check
        )
        client.force_login(nurse_a)
        resp = client.patch(
            f"/api/shifts/{shift.pk}/end/",
            json.dumps({}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_doctor_cannot_start_shift(self, db, client, doctor_a):
        client.force_login(doctor_a)
        resp = client.post(
            "/api/shifts/start/",
            json.dumps({}),
            content_type="application/json",
        )
        assert resp.status_code == 403


# ══════════════════════════════════════════════════════════════════════════════
# Vitals
# ══════════════════════════════════════════════════════════════════════════════


class TestVitals:
    def _url(self, patient):
        return f"/api/patients/{patient.universal_id}/vitals/"

    def test_nurse_can_record_vitals(self, db, client, nurse_a, patient_a):
        client.force_login(nurse_a)
        resp = client.post(
            self._url(patient_a),
            json.dumps({"heart_rate": 72, "temperature": "36.8"}),
            content_type="application/json",
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["heart_rate"] == 72

    def test_vitals_creates_audit_row(self, db, client, nurse_a, patient_a):
        client.force_login(nurse_a)
        client.post(
            self._url(patient_a),
            json.dumps({"heart_rate": 80}),
            content_type="application/json",
        )
        assert AuditLog.objects.filter(action="CREATE_VITAL").exists()

    def test_receptionist_cannot_record_vitals(self, db, client, hospital_a, patient_a):
        recept = _make_user("recept_vitals_pb", "receptionist", hospital_a)
        client.force_login(recept)
        resp = client.post(
            self._url(patient_a),
            json.dumps({"heart_rate": 72}),
            content_type="application/json",
        )
        assert resp.status_code == 403

    def test_cross_hospital_cannot_read_vitals(self, db, client, doctor_b, patient_a):
        client.force_login(doctor_b)
        resp = client.get(self._url(patient_a))
        assert resp.status_code == 403

    def test_doctor_can_record_vitals(self, db, client, doctor_a, patient_a):
        client.force_login(doctor_a)
        resp = client.post(
            self._url(patient_a),
            json.dumps({"bp_systolic": 120, "bp_diastolic": 80}),
            content_type="application/json",
        )
        assert resp.status_code == 201

    def test_vitals_out_of_bounds_rejected_with_400(self, db, client, nurse_a, patient_a):
        client.force_login(nurse_a)
        # Heart rate < 20 or > 300
        resp = client.post(
            self._url(patient_a),
            json.dumps({"heart_rate": -500}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "heart_rate" in resp.json()

        resp = client.post(
            self._url(patient_a),
            json.dumps({"heart_rate": 30000}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "heart_rate" in resp.json()

        # Temperature < 30 or > 45
        resp = client.post(
            self._url(patient_a),
            json.dumps({"temperature": "25.0"}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "temperature" in resp.json()

        resp = client.post(
            self._url(patient_a),
            json.dumps({"temperature": "50.0"}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "temperature" in resp.json()

        # SpO2 < 50 or > 100
        resp = client.post(
            self._url(patient_a),
            json.dumps({"spo2": "40.0"}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "spo2" in resp.json()

        resp = client.post(
            self._url(patient_a),
            json.dumps({"spo2": "200.0"}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "spo2" in resp.json()

        # Pain score > 10
        resp = client.post(
            self._url(patient_a),
            json.dumps({"pain_score": 11}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "pain_score" in resp.json()

        # BP systolic < 50 or > 250
        resp = client.post(
            self._url(patient_a),
            json.dumps({"bp_systolic": 40}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "bp_systolic" in resp.json()

        resp = client.post(
            self._url(patient_a),
            json.dumps({"bp_systolic": 300}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "bp_systolic" in resp.json()

        # BP diastolic < 30 or > 150
        resp = client.post(
            self._url(patient_a),
            json.dumps({"bp_diastolic": 20}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "bp_diastolic" in resp.json()

        resp = client.post(
            self._url(patient_a),
            json.dumps({"bp_diastolic": 160}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "bp_diastolic" in resp.json()

        # Blood glucose < 0.5 or > 50.0
        resp = client.post(
            self._url(patient_a),
            json.dumps({"blood_glucose": "0.1"}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "blood_glucose" in resp.json()

        resp = client.post(
            self._url(patient_a),
            json.dumps({"blood_glucose": "55.0"}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "blood_glucose" in resp.json()

    def test_vitals_systolic_must_exceed_diastolic(self, db, client, doctor_a, patient_a):
        client.force_login(doctor_a)
        # Systolic < Diastolic
        resp = client.post(
            self._url(patient_a),
            json.dumps({"bp_systolic": 80, "bp_diastolic": 120}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "bp_systolic" in resp.json()

        # Systolic == Diastolic
        resp = client.post(
            self._url(patient_a),
            json.dumps({"bp_systolic": 100, "bp_diastolic": 100}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "bp_systolic" in resp.json()

    def test_vitals_valid_boundaries_accepted(self, db, client, nurse_a, patient_a):
        client.force_login(nurse_a)
        resp = client.post(
            self._url(patient_a),
            json.dumps(
                {
                    "temperature": "30.0",
                    "heart_rate": 20,
                    "bp_systolic": 50,
                    "bp_diastolic": 30,
                    "spo2": "50.00",
                    "pain_score": 0,
                    "blood_glucose": "0.5",
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 201
        assert float(resp.json()["blood_glucose"]) == 0.5

        resp = client.post(
            self._url(patient_a),
            json.dumps(
                {
                    "temperature": "45.0",
                    "heart_rate": 300,
                    "bp_systolic": 250,
                    "bp_diastolic": 150,
                    "spo2": "100.00",
                    "pain_score": 10,
                    "blood_glucose": "50.0",
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 201
        assert float(resp.json()["blood_glucose"]) == 50.0

    def test_vitals_model_full_clean_validates_boundaries(self, db, patient_a, nurse_a):
        from django.core.exceptions import ValidationError

        from records.models import VitalSign

        vital = VitalSign(
            patient=patient_a,
            recorded_by=nurse_a,
            heart_rate=10,
        )
        with pytest.raises(ValidationError):
            vital.full_clean()

    def test_vitals_model_clean_rejects_systolic_lte_diastolic(self, db, patient_a, nurse_a):
        from django.core.exceptions import ValidationError

        from records.models import VitalSign

        vital = VitalSign(
            patient=patient_a,
            recorded_by=nurse_a,
            bp_systolic=90,
            bp_diastolic=110,
        )
        with pytest.raises(ValidationError) as excinfo:
            vital.clean()
        assert "bp_systolic" in excinfo.value.message_dict

    def test_vitals_respiratory_rate_and_weight_boundaries(self, db, client, nurse_a, patient_a):
        client.force_login(nurse_a)
        # Respiratory rate out of bounds (< 4 or > 80)
        resp = client.post(
            self._url(patient_a),
            json.dumps({"respiratory_rate": 100}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "respiratory_rate" in resp.json()

        # Weight out of bounds (< 0.5 or > 500)
        resp = client.post(
            self._url(patient_a),
            json.dumps({"weight_kg": "600.0"}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "weight_kg" in resp.json()

    def test_db_check_constraints_reject_out_of_range(self, db, patient_a, nurse_a):
        from decimal import Decimal

        from django.db import IntegrityError, transaction

        from records.models import VitalSign

        # Heart rate out of range at DB layer
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                VitalSign.objects.create(
                    patient=patient_a,
                    recorded_by=nurse_a,
                    heart_rate=500,
                )

        # SpO2 out of range at DB layer
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                VitalSign.objects.create(
                    patient=patient_a,
                    recorded_by=nurse_a,
                    spo2=Decimal("150.0"),
                )


# ══════════════════════════════════════════════════════════════════════════════
# Lab Orders
# ══════════════════════════════════════════════════════════════════════════════


class TestLabOrders:
    def _url(self, patient):
        return f"/api/patients/{patient.universal_id}/lab-orders/"

    def test_doctor_can_place_lab_order(self, db, client, doctor_a, patient_a, encounter_a):
        client.force_login(doctor_a)
        resp = client.post(
            self._url(patient_a),
            json.dumps(
                {
                    "test_name": "Full Blood Count",
                    "priority": "routine",
                    "encounter": encounter_a.pk,
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 201
        assert resp.json()["test_name"] == "Full Blood Count"

    def test_lab_order_creates_audit_row(self, db, client, doctor_a, patient_a):
        client.force_login(doctor_a)
        client.post(
            self._url(patient_a),
            json.dumps({"test_name": "Malaria RDT", "priority": "stat"}),
            content_type="application/json",
        )
        assert AuditLog.objects.filter(action="CREATE_LAB_ORDER").exists()

    def test_lab_tech_cannot_place_order(self, db, client, lab_tech_a, patient_a):
        client.force_login(lab_tech_a)
        resp = client.post(
            self._url(patient_a),
            json.dumps({"test_name": "CBC", "priority": "routine"}),
            content_type="application/json",
        )
        assert resp.status_code == 403

    def test_lab_tech_can_update_status(self, db, client, lab_tech_a, doctor_a, patient_a):
        from records.models import LabOrder

        order = LabOrder.objects.create(
            patient=patient_a,
            ordered_by=doctor_a,
            test_name="Liver Function Test",
            priority="routine",
        )
        client.force_login(lab_tech_a)
        resp = client.patch(
            f"/api/lab-orders/{order.pk}/status/",
            json.dumps({"status": "in_progress"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "in_progress"

    def test_invalid_status_rejected(self, db, client, lab_tech_a, doctor_a, patient_a):
        from records.models import LabOrder

        order = LabOrder.objects.create(
            patient=patient_a, ordered_by=doctor_a, test_name="CRP", priority="urgent"
        )
        client.force_login(lab_tech_a)
        resp = client.patch(
            f"/api/lab-orders/{order.pk}/status/",
            json.dumps({"status": "BOGUS"}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_worklist_returns_pending_orders(self, db, client, lab_tech_a, doctor_a, patient_a):
        from records.models import LabOrder

        LabOrder.objects.create(
            patient=patient_a,
            ordered_by=doctor_a,
            test_name="ESR",
            priority="routine",
            status="pending",
        )
        LabOrder.objects.create(
            patient=patient_a,
            ordered_by=doctor_a,
            test_name="Troponin",
            priority="stat",
            status="resulted",
        )
        client.force_login(lab_tech_a)
        resp = client.get("/api/lab-orders/worklist/")
        assert resp.status_code == 200
        names = [o["test_name"] for o in resp.json()]
        assert "ESR" in names
        assert "Troponin" not in names


# ══════════════════════════════════════════════════════════════════════════════
# Staff — reset-password endpoint
# ══════════════════════════════════════════════════════════════════════════════


class TestStaffResetPassword:
    def _url(self, user):
        return f"/api/staff/{user.pk}/reset-password/"

    STRONG_PW = "NewStr0ng!Pass99"

    def test_hospital_admin_can_reset_same_hospital_staff(
        self, db, client, hosp_admin_a, target_staff_a
    ):
        client.force_login(hosp_admin_a)
        resp = client.post(
            self._url(target_staff_a),
            json.dumps({"password": self.STRONG_PW}),
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_reset_password_creates_audit_row(self, db, client, hosp_admin_a, target_staff_a):
        client.force_login(hosp_admin_a)
        client.post(
            self._url(target_staff_a),
            json.dumps({"password": self.STRONG_PW}),
            content_type="application/json",
        )
        assert AuditLog.objects.filter(action="RESET_STAFF_PASSWORD").exists()

    def test_self_reset_blocked(self, db, client, hosp_admin_a):
        client.force_login(hosp_admin_a)
        resp = client.post(
            self._url(hosp_admin_a),
            json.dumps({"password": self.STRONG_PW}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_cross_hospital_blocked_for_hospital_admin(self, db, client, hosp_admin_a, nurse_b):
        """hospital_admin cannot reset password for staff at another hospital."""
        client.force_login(hosp_admin_a)
        resp = client.post(
            self._url(nurse_b),
            json.dumps({"password": self.STRONG_PW}),
            content_type="application/json",
        )
        assert resp.status_code == 403

    def test_weak_password_rejected(self, db, client, hosp_admin_a, target_staff_a):
        # Test settings disable all validators — enable MinimumLengthValidator
        # explicitly so the view rejects a clearly-too-short password.
        from django.test import override_settings

        validators = [
            {
                "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
                "OPTIONS": {"min_length": 12},
            }
        ]
        with override_settings(AUTH_PASSWORD_VALIDATORS=validators):
            client.force_login(hosp_admin_a)
            resp = client.post(
                self._url(target_staff_a),
                json.dumps({"password": "weak"}),
                content_type="application/json",
            )
        assert resp.status_code == 400

    def test_missing_password_rejected(self, db, client, hosp_admin_a, target_staff_a):
        client.force_login(hosp_admin_a)
        resp = client.post(
            self._url(target_staff_a),
            json.dumps({}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_super_admin_can_reset_any(self, db, client, sys_admin, target_staff_a):
        client.force_login(sys_admin)
        resp = client.post(
            self._url(target_staff_a),
            json.dumps({"password": self.STRONG_PW}),
            content_type="application/json",
        )
        assert resp.status_code == 200
