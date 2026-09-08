"""
Tests for audit logging on ePHI read endpoints.

Verifies that accessing sensitive ePHI read paths triggers audit log creation:
  - GET /api/appointments/ (VIEW_APPOINTMENTS)
  - GET /api/appointments/<pk>/ (VIEW_APPOINTMENT)
  - GET /api/referrals/ (VIEW_REFERRALS)
  - GET /api/wards/ (VIEW_WARDS)
  - GET /api/wards/<pk>/ (VIEW_WARD)
  - GET /api/med-admins/ (VIEW_MAR)
  - GET /api/alerts/ (VIEW_ALERTS)
  - GET /api/patients/<nhid>/lab-orders/ (VIEW_LAB_ORDERS)
  - GET /api/lab-orders/<pk>/ (VIEW_LAB_ORDER)
  - GET /api/lab-orders/worklist/ (VIEW_LAB_WORKLIST)
  - GET /api/handovers/ (VIEW_HANDOVERS)
  - Verification that newly generated read audit logs maintain hash chain validity.
"""

import pytest
from django.core.management import call_command
from django.utils import timezone

from audit.models import AuditLog
from hospitals.models import Bed, Ward
from records.models import Encounter, LabOrder, LabResult, MedicationAdministration, Prescription
from referrals.models import Referral
from scheduling.models import Appointment
from shifts.models import Handover, ShiftRecord


@pytest.mark.django_db
class TestAuditReadEndpoints:

    def test_view_appointments_list_audited(self, client_as_doctor_a, hospital_a, patient_a, doctor_a):
        Appointment.objects.create(
            patient=patient_a,
            provider=doctor_a,
            hospital=hospital_a,
            scheduled_for=timezone.now() + timezone.timedelta(days=1),
            reason="Checkup",
            created_by=doctor_a,
        )
        initial_count = AuditLog.objects.filter(action=AuditLog.Action.VIEW_APPOINTMENTS).count()

        resp = client_as_doctor_a.get("/api/appointments/")
        assert resp.status_code == 200

        entry = AuditLog.objects.filter(action=AuditLog.Action.VIEW_APPOINTMENTS).latest("timestamp")
        assert entry.actor == doctor_a
        assert entry.extra.get("count") >= 1
        assert AuditLog.objects.filter(action=AuditLog.Action.VIEW_APPOINTMENTS).count() == initial_count + 1

    def test_view_appointment_detail_audited(self, client_as_doctor_a, hospital_a, patient_a, doctor_a):
        appt = Appointment.objects.create(
            patient=patient_a,
            provider=doctor_a,
            hospital=hospital_a,
            scheduled_for=timezone.now() + timezone.timedelta(days=1),
            reason="Follow-up",
            created_by=doctor_a,
        )

        resp = client_as_doctor_a.get(f"/api/appointments/{appt.pk}/")
        assert resp.status_code == 200

        entry = AuditLog.objects.filter(action=AuditLog.Action.VIEW_APPOINTMENT).latest("timestamp")
        assert entry.actor == doctor_a
        assert entry.target_id == str(appt.pk)
        assert entry.patient_nhid == patient_a.universal_id
        assert entry.is_cross_hospital is False

    def test_view_referrals_list_audited(self, client_as_doctor_a, hospital_a, hospital_b, patient_a, doctor_a):
        Referral.objects.create(
            patient=patient_a,
            from_hospital=hospital_a,
            to_hospital=hospital_b,
            from_provider=doctor_a,
            reason="Specialist consult",
        )

        resp = client_as_doctor_a.get("/api/referrals/")
        assert resp.status_code == 200

        entry = AuditLog.objects.filter(action=AuditLog.Action.VIEW_REFERRALS).latest("timestamp")
        assert entry.actor == doctor_a
        assert entry.extra.get("count") >= 1

    def test_view_wards_and_detail_audited(self, client_as_hospital_admin_a, hospital_a, patient_a):
        ward = Ward.objects.create(
            hospital=hospital_a,
            name="Male Medical Ward",
            code="MMW",
            capacity=10,
        )
        Bed.objects.create(ward=ward, label="Bed 1", current_patient=patient_a, status="occupied")

        # List wards
        resp_list = client_as_hospital_admin_a.get("/api/wards/")
        assert resp_list.status_code == 200
        list_entry = AuditLog.objects.filter(action=AuditLog.Action.VIEW_WARDS).latest("timestamp")
        assert list_entry.extra.get("count") >= 1

        # Ward detail
        resp_detail = client_as_hospital_admin_a.get(f"/api/wards/{ward.pk}/")
        assert resp_detail.status_code == 200
        detail_entry = AuditLog.objects.filter(action=AuditLog.Action.VIEW_WARD).latest("timestamp")
        assert detail_entry.target_id == str(ward.pk)
        assert detail_entry.extra.get("ward_code") == "MMW"

    def test_view_mar_audited(self, client_as_doctor_a, patient_a, doctor_a, hospital_a):
        encounter = Encounter.objects.create(
            patient=patient_a,
            encounter_type="OPD",
            chief_complaint="Asthma exacerbation",
            created_by=doctor_a,
            created_at_hospital=hospital_a,
        )
        rx = Prescription.objects.create(
            encounter=encounter,
            drug_name="Salbutamol",
            dosage="2 puffs",
            frequency="TDS",
            created_by=doctor_a,
        )
        MedicationAdministration.objects.create(
            prescription=rx,
            scheduled_time=timezone.now(),
            status="due",
        )

        # Scoped by patient
        resp = client_as_doctor_a.get(f"/api/med-admins/?patient={patient_a.universal_id}")
        assert resp.status_code == 200

        entry = AuditLog.objects.filter(action=AuditLog.Action.VIEW_MAR).latest("timestamp")
        assert entry.actor == doctor_a
        assert entry.patient_nhid == patient_a.universal_id
        assert entry.is_cross_hospital is False
        assert entry.extra.get("count") >= 1

    def test_view_alerts_feed_audited(self, client_as_doctor_a, doctor_a, encounter_a):
        LabResult.objects.create(
            encounter=encounter_a,
            test_name="Potassium",
            result_value="6.5 mmol/L (CRITICAL HIGH)",
            is_abnormal=True,
            created_by=doctor_a,
        )

        resp = client_as_doctor_a.get("/api/alerts/")
        assert resp.status_code == 200

        entry = AuditLog.objects.filter(action=AuditLog.Action.VIEW_ALERTS).latest("timestamp")
        assert entry.actor == doctor_a
        assert entry.extra.get("count") >= 1

    def test_view_lab_orders_audited(self, client_as_doctor_a, patient_a, doctor_a, encounter_a, hospital_a):
        order = LabOrder.objects.create(
            encounter=encounter_a,
            patient=patient_a,
            ordered_by=doctor_a,
            test_name="Full Blood Count",
            priority="routine",
            status="pending",
        )

        # 1. Patient lab orders list
        resp_list = client_as_doctor_a.get(f"/api/patients/{patient_a.universal_id}/lab-orders/")
        assert resp_list.status_code == 200
        entry_list = AuditLog.objects.filter(action=AuditLog.Action.VIEW_LAB_ORDERS).latest("timestamp")
        assert entry_list.patient_nhid == patient_a.universal_id
        assert entry_list.actor == doctor_a

        # 2. Lab order detail
        resp_detail = client_as_doctor_a.get(f"/api/lab-orders/{order.pk}/")
        assert resp_detail.status_code == 200
        entry_detail = AuditLog.objects.filter(action=AuditLog.Action.VIEW_LAB_ORDER).latest("timestamp")
        assert entry_detail.target_id == str(order.pk)
        assert entry_detail.patient_nhid == patient_a.universal_id

        # 3. Lab order worklist
        resp_worklist = client_as_doctor_a.get("/api/lab-orders/worklist/")
        assert resp_worklist.status_code == 200
        entry_worklist = AuditLog.objects.filter(action=AuditLog.Action.VIEW_LAB_WORKLIST).latest("timestamp")
        assert entry_worklist.actor == doctor_a
        assert entry_worklist.extra.get("count") >= 1

    def test_view_handovers_audited(self, client, nurse_a, hospital_a):
        client.force_login(nurse_a)
        shift = ShiftRecord.objects.create(
            user=nurse_a,
            started_at=timezone.now(),
        )
        Handover.objects.create(
            shift=shift,
            from_user=nurse_a,
            summary="Patients stable in ward.",
        )

        resp = client.get("/api/handovers/")
        assert resp.status_code == 200

        entry = AuditLog.objects.filter(action=AuditLog.Action.VIEW_HANDOVERS).latest("timestamp")
        assert entry.actor == nurse_a
        assert entry.extra.get("count") >= 1

    def test_read_audit_entries_maintain_hash_chain_integrity(self, client_as_doctor_a, patient_a, doctor_a, hospital_a):
        # Trigger multiple read operations in sequence
        client_as_doctor_a.get("/api/appointments/")
        client_as_doctor_a.get(f"/api/patients/{patient_a.universal_id}/lab-orders/")
        client_as_doctor_a.get("/api/alerts/")

        # Verify hash chain integrity across all entries
        call_command("verify_audit_chain")
