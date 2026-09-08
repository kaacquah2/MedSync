"""
Tests for Emergency Triage Acuity enum field, validation, API views, and sorting.

Verifies:
  - Appointment model validates triage_acuity is required for EMERGENCY appointments.
  - Non-emergency appointments can have triage_acuity=None.
  - AppointmentSerializer requires and validates triage_acuity for emergency appointments.
  - Backward compatibility: triage_level in API input maps to triage_acuity.
  - API view filters by appointment_type and triage_acuity.
  - Legacy triage notes migration backfills triage_acuity.
"""

import importlib

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework.test import APIClient

from scheduling.models import Appointment

migration_module = importlib.import_module("scheduling.migrations.0005_appointment_triage_acuity")
backfill_triage_acuity = migration_module.backfill_triage_acuity


@pytest.mark.django_db
class TestEmergencyTriageModel:
    def test_emergency_appointment_requires_triage_acuity(self, patient_a, hospital_a, doctor_a):
        appt = Appointment(
            patient=patient_a,
            hospital=hospital_a,
            created_by=doctor_a,
            scheduled_for=timezone.now(),
            appointment_type=Appointment.AppointmentType.EMERGENCY,
            triage_acuity=None,
        )
        with pytest.raises(ValidationError) as excinfo:
            appt.full_clean()
        assert "triage_acuity" in excinfo.value.message_dict

    def test_emergency_appointment_with_valid_acuity_succeeds(
        self, patient_a, hospital_a, doctor_a
    ):
        for acuity in [
            Appointment.TriageAcuity.RED,
            Appointment.TriageAcuity.ORANGE,
            Appointment.TriageAcuity.YELLOW,
            Appointment.TriageAcuity.GREEN,
        ]:
            appt = Appointment.objects.create(
                patient=patient_a,
                hospital=hospital_a,
                created_by=doctor_a,
                scheduled_for=timezone.now(),
                appointment_type=Appointment.AppointmentType.EMERGENCY,
                triage_acuity=acuity,
            )
            appt.full_clean()
            assert appt.triage_acuity == acuity

    def test_outpatient_appointment_without_triage_acuity_succeeds(
        self, patient_a, hospital_a, doctor_a
    ):
        appt = Appointment.objects.create(
            patient=patient_a,
            hospital=hospital_a,
            created_by=doctor_a,
            scheduled_for=timezone.now(),
            appointment_type=Appointment.AppointmentType.OUTPATIENT,
            triage_acuity=None,
        )
        appt.full_clean()
        assert appt.triage_acuity is None


@pytest.mark.django_db
class TestEmergencyTriageAPI:
    @pytest.fixture
    def auth_doctor_client(self, doctor_a):
        client = APIClient()
        client.force_authenticate(user=doctor_a)
        return client

    def test_create_emergency_appointment_success(self, auth_doctor_client, patient_a, hospital_a):
        payload = {
            "patient": patient_a.pk,
            "appointment_type": "emergency",
            "status": "checked_in",
            "scheduled_for": timezone.now().isoformat(),
            "triage_acuity": "RED",
            "reason": "Severe chest pain, diaphoresis",
            "notes": "ECG ordered immediately",
        }
        resp = auth_doctor_client.post("/api/appointments/", payload, format="json")
        assert resp.status_code == 201
        data = resp.json()
        assert data["triage_acuity"] == "RED"
        assert data["triage_acuity_display"] == "Red - Resuscitation"
        assert data["triage_level"] == "RED"

    def test_create_emergency_appointment_missing_acuity_fails(self, auth_doctor_client, patient_a):
        payload = {
            "patient": patient_a.pk,
            "appointment_type": "emergency",
            "status": "checked_in",
            "scheduled_for": timezone.now().isoformat(),
            "reason": "Cardiac arrest",
        }
        resp = auth_doctor_client.post("/api/appointments/", payload, format="json")
        assert resp.status_code == 400
        assert "triage_acuity" in resp.json()

    def test_create_emergency_appointment_with_triage_level_alias(
        self, auth_doctor_client, patient_a
    ):
        payload = {
            "patient": patient_a.pk,
            "appointment_type": "emergency",
            "status": "checked_in",
            "scheduled_for": timezone.now().isoformat(),
            "triage_level": "ORANGE",
            "reason": "Fractured femur with high pain",
        }
        resp = auth_doctor_client.post("/api/appointments/", payload, format="json")
        assert resp.status_code == 201
        data = resp.json()
        assert data["triage_acuity"] == "ORANGE"
        assert data["triage_level"] == "ORANGE"

    def test_create_emergency_appointment_invalid_acuity_fails(self, auth_doctor_client, patient_a):
        payload = {
            "patient": patient_a.pk,
            "appointment_type": "emergency",
            "status": "checked_in",
            "scheduled_for": timezone.now().isoformat(),
            "triage_acuity": "PURPLE",
            "reason": "Invalid acuity test",
        }
        resp = auth_doctor_client.post("/api/appointments/", payload, format="json")
        assert resp.status_code == 400
        assert "triage_acuity" in resp.json()

    def test_filter_appointments_by_type_and_acuity(
        self, auth_doctor_client, patient_a, hospital_a, doctor_a
    ):
        # Create RED emergency
        Appointment.objects.create(
            patient=patient_a,
            hospital=hospital_a,
            created_by=doctor_a,
            scheduled_for=timezone.now(),
            appointment_type="emergency",
            triage_acuity="RED",
            status="checked_in",
        )
        # Create YELLOW emergency
        Appointment.objects.create(
            patient=patient_a,
            hospital=hospital_a,
            created_by=doctor_a,
            scheduled_for=timezone.now(),
            appointment_type="emergency",
            triage_acuity="YELLOW",
            status="checked_in",
        )
        # Create outpatient
        Appointment.objects.create(
            patient=patient_a,
            hospital=hospital_a,
            created_by=doctor_a,
            scheduled_for=timezone.now(),
            appointment_type="outpatient",
            status="checked_in",
        )

        resp_emrg = auth_doctor_client.get("/api/appointments/?appointment_type=emergency")
        assert resp_emrg.status_code == 200
        assert len(resp_emrg.json()) == 2

        resp_red = auth_doctor_client.get("/api/appointments/?triage_acuity=RED")
        assert resp_red.status_code == 200
        assert len(resp_red.json()) == 1
        assert resp_red.json()[0]["triage_acuity"] == "RED"


@pytest.mark.django_db
class TestLegacyTriageBackfill:
    def test_backfill_triage_acuity(self, patient_a, hospital_a, doctor_a):
        # Create legacy emergency appointment with [Triage: RED] in notes
        appt1 = Appointment(
            patient=patient_a,
            hospital=hospital_a,
            created_by=doctor_a,
            scheduled_for=timezone.now(),
            appointment_type=Appointment.AppointmentType.EMERGENCY,
            notes="[Triage: RED] Severe head trauma, GCS 8",
            triage_acuity=None,
        )
        # Bypass clean() for legacy simulation
        appt1.save()

        # Create legacy emergency appointment with [Triage: ORANGE] in reason
        appt2 = Appointment(
            patient=patient_a,
            hospital=hospital_a,
            created_by=doctor_a,
            scheduled_for=timezone.now(),
            appointment_type=Appointment.AppointmentType.EMERGENCY,
            reason="[Triage: ORANGE] Acute asthma exacerbation",
            triage_acuity=None,
        )
        appt2.save()

        # Mock apps for migration function
        class MockApps:
            @staticmethod
            def get_model(app_label, model_name):
                return Appointment

        backfill_triage_acuity(MockApps, None)

        appt1.refresh_from_db()
        appt2.refresh_from_db()

        assert appt1.triage_acuity == "RED"
        assert appt2.triage_acuity == "ORANGE"
