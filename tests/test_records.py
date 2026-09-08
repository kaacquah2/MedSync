"""
Tests for the clinical records (Encounter, Diagnosis, Prescription, LabResult).

Verifies:
  - Encounter creation via API stamps created_by and created_at_hospital
  - Encrypted fields (chief_complaint, drug_name) stored as ciphertext in DB
  - Prescription creation restricted to DOCTOR role
  - Lab result creation allowed for LAB_TECH, DOCTOR, NURSE
"""

import json

import pytest

from records.models import Diagnosis, Encounter, LabResult, Prescription


class TestEncounterCreation:
    def test_create_encounter_via_api(self, client_as_doctor_a, patient_a):
        resp = client_as_doctor_a.post(
            f"/api/patients/{patient_a.universal_id}/encounters/",
            json.dumps({"encounter_type": "OPD", "chief_complaint": "Headache and fever"}),
            content_type="application/json",
        )
        assert resp.status_code == 201
        enc = Encounter.objects.filter(patient=patient_a).first()
        assert enc is not None
        assert enc.chief_complaint == "Headache and fever"

    def test_encounter_stamps_created_by(self, client_as_doctor_a, patient_a, doctor_a):
        client_as_doctor_a.post(
            f"/api/patients/{patient_a.universal_id}/encounters/",
            json.dumps({"encounter_type": "OPD", "chief_complaint": "Test complaint"}),
            content_type="application/json",
        )
        enc = Encounter.objects.filter(patient=patient_a).first()
        assert enc.created_by == doctor_a

    def test_encounter_stamps_hospital(self, client_as_doctor_a, patient_a, hospital_a):
        client_as_doctor_a.post(
            f"/api/patients/{patient_a.universal_id}/encounters/",
            json.dumps({"encounter_type": "OPD", "chief_complaint": "Test complaint"}),
            content_type="application/json",
        )
        enc = Encounter.objects.filter(patient=patient_a).first()
        assert enc.created_at_hospital == hospital_a

    def test_chief_complaint_encrypted_in_db(self, db, encounter_a):
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT chief_complaint FROM records_encounter WHERE id = %s",
                [encounter_a.pk],
            )
            raw = cursor.fetchone()[0]
        assert raw.startswith("gAAAAA"), "Chief complaint must be encrypted in DB"
        assert "Fever" not in raw

    def test_encounter_status_default_is_open(self, db, patient_a, doctor_a):
        enc = Encounter.objects.create(
            patient=patient_a,
            created_by=doctor_a,
            chief_complaint="Chest pain",
        )
        assert enc.status == Encounter.Status.OPEN
        assert enc.get_status_display() == "Open"

    def test_encounter_validation_empty_complaint(self, client_as_doctor_a, patient_a):
        resp = client_as_doctor_a.post(
            f"/api/patients/{patient_a.universal_id}/encounters/",
            json.dumps({"encounter_type": "OPD", "chief_complaint": "   "}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "Chief complaint is required." in resp.json().get("error", "")

    def test_encounter_validation_invalid_type(self, client_as_doctor_a, patient_a):
        resp = client_as_doctor_a.post(
            f"/api/patients/{patient_a.universal_id}/encounters/",
            json.dumps({"encounter_type": "INVALID_TYPE", "chief_complaint": "Valid complaint"}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "encounter_type" in resp.json()


class TestDiagnosisCreation:
    def test_doctor_can_add_diagnosis(self, client_as_doctor_a, encounter_a):
        resp = client_as_doctor_a.post(
            f"/api/encounters/{encounter_a.pk}/diagnoses/",
            json.dumps(
                {
                    "icd_code": "J06.9",
                    "description": "Upper respiratory infection",
                    "is_primary": True,
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 201
        assert Diagnosis.objects.filter(encounter=encounter_a).exists()

    def test_nurse_cannot_add_diagnosis(self, db, nurse_a, encounter_a, client):
        client.force_login(nurse_a)
        resp = client.post(
            f"/api/encounters/{encounter_a.pk}/diagnoses/",
            json.dumps({"icd_code": "R51.9", "description": "Headache", "is_primary": True}),
            content_type="application/json",
        )
        assert resp.status_code == 403
        assert not Diagnosis.objects.filter(encounter=encounter_a, description="Headache").exists()


class TestPrescriptionRBAC:
    def test_doctor_can_prescribe(self, client_as_doctor_a, encounter_a):
        resp = client_as_doctor_a.post(
            f"/api/encounters/{encounter_a.pk}/prescriptions/",
            json.dumps({"drug_name": "Paracetamol", "dosage": "500mg", "frequency": "8h"}),
            content_type="application/json",
        )
        assert resp.status_code == 201
        assert Prescription.objects.filter(encounter=encounter_a).exists()

    def test_nurse_cannot_prescribe(self, db, nurse_a, encounter_a, client):
        client.force_login(nurse_a)
        resp = client.post(
            f"/api/encounters/{encounter_a.pk}/prescriptions/",
            json.dumps({"drug_name": "Paracetamol", "dosage": "500mg", "frequency": "8h"}),
            content_type="application/json",
        )
        assert resp.status_code == 403

    def test_prescription_drug_name_encrypted(self, db, doctor_a, encounter_a, client):
        client.force_login(doctor_a)
        client.post(
            f"/api/encounters/{encounter_a.pk}/prescriptions/",
            json.dumps({"drug_name": "Metformin 500mg", "dosage": "500mg", "frequency": "daily"}),
            content_type="application/json",
        )
        from django.db import connection

        rx = Prescription.objects.filter(encounter=encounter_a).first()
        with connection.cursor() as cursor:
            cursor.execute("SELECT drug_name FROM records_prescription WHERE id = %s", [rx.pk])
            raw = cursor.fetchone()[0]
        assert raw.startswith("gAAAAA")
        assert "Metformin" not in raw


class TestLabResults:
    def test_lab_tech_can_add_result(self, db, hospital_a, encounter_a, client):
        from accounts.models import User

        lab_tech = User.objects.create_user(
            username="labtech_t",
            password="Test@password1",
            role="lab_technician",
            hospital=hospital_a,
        )
        client.force_login(lab_tech)
        resp = client.post(
            f"/api/encounters/{encounter_a.pk}/lab-results/",
            json.dumps(
                {
                    "test_name": "FBC",
                    "result_value": "WBC 5.5 × 10^9/L",
                    "reference_range": "4-11",
                    "is_abnormal": False,
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 201
        assert LabResult.objects.filter(encounter=encounter_a).exists()

    def test_nurse_cannot_add_lab_result(self, db, nurse_a, encounter_a, client):
        client.force_login(nurse_a)
        resp = client.post(
            f"/api/encounters/{encounter_a.pk}/lab-results/",
            json.dumps(
                {
                    "test_name": "FBC",
                    "result_value": "WBC 5.5 × 10^9/L",
                    "reference_range": "4-11",
                    "is_abnormal": False,
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 403

    def test_lab_tech_can_add_result_with_order_links_and_results(
        self, db, hospital_a, encounter_a, patient_a, doctor_a, client
    ):
        from accounts.models import User
        from records.models import LabOrder

        lab_tech = User.objects.create_user(
            username="labtech_order",
            password="Test@password1",
            role="lab_technician",
            hospital=hospital_a,
        )
        order = LabOrder.objects.create(
            encounter=encounter_a,
            patient=patient_a,
            ordered_by=doctor_a,
            test_name="FBC",
            priority="routine",
            status="pending",
        )
        client.force_login(lab_tech)
        resp = client.post(
            f"/api/encounters/{encounter_a.pk}/lab-results/",
            json.dumps(
                {
                    "order_id": order.id,
                    "test_name": "FBC",
                    "result_value": "WBC 6.0 × 10^9/L",
                    "reference_range": "4-11",
                    "is_abnormal": False,
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 201
        order.refresh_from_db()
        assert order.status == LabOrder.Status.RESULTED
        lab = LabResult.objects.get(pk=resp.data["id"])
        assert lab.order == order
        assert lab.is_critical is False
        assert resp.data["doctor_notified"] is False

    def test_critical_result_creates_patient_alert_and_notifies_doctor(
        self, db, hospital_a, encounter_a, patient_a, doctor_a, client
    ):
        from accounts.models import User
        from django.core import mail
        from audit.models import AuditLog
        from patients.models import PatientAlert
        from records.models import LabOrder

        doctor_a.email = "attending_doc@ugmc.gov.gh"
        doctor_a.save()

        lab_tech = User.objects.create_user(
            username="labtech_crit",
            password="Test@password1",
            role="lab_technician",
            hospital=hospital_a,
        )
        order = LabOrder.objects.create(
            encounter=encounter_a,
            patient=patient_a,
            ordered_by=doctor_a,
            test_name="Potassium",
            priority="urgent",
            status="pending",
        )
        mail.outbox.clear()
        client.force_login(lab_tech)
        resp = client.post(
            f"/api/encounters/{encounter_a.pk}/lab-results/",
            json.dumps(
                {
                    "order_id": order.id,
                    "test_name": "Potassium",
                    "result_value": "7.2 mmol/L (CRITICAL HIGH)",
                    "reference_range": "3.5-5.0",
                    "is_critical": True,
                    "notify_doctor": True,
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 201
        data = resp.data
        assert data["is_critical"] is True
        assert data["is_abnormal"] is True
        assert data["doctor_notified"] is True
        assert data["doctor_name"] is not None
        assert data["patient_alert_id"] is not None

        # Originating order is marked resulted
        order.refresh_from_db()
        assert order.status == LabOrder.Status.RESULTED

        # Emergency PatientAlert was created
        alert = PatientAlert.objects.get(pk=data["patient_alert_id"])
        assert alert.patient == patient_a
        assert alert.kind == PatientAlert.Kind.ALERT
        assert alert.severity == PatientAlert.Severity.LIFE_THREAT
        assert "Potassium" in alert.label

        # Notification email was sent to ordering doctor
        assert len(mail.outbox) == 1
        sent_email = mail.outbox[0]
        assert "URGENT" in sent_email.subject
        assert doctor_a.email in sent_email.to
        assert "7.2 mmol/L" in sent_email.body

        # Doctor's alerts feed contains the critical lab result as LIFE_THREAT
        client.force_login(doctor_a)
        feed_resp = client.get("/api/alerts/")
        assert feed_resp.status_code == 200
        feed_results = feed_resp.data["results"]
        matching_lab_alert = next((a for a in feed_results if a["id"] == f"lab-{data['id']}"), None)
        assert matching_lab_alert is not None
        assert matching_lab_alert["severity"] == "LIFE_THREAT"
        assert "CRITICAL" in matching_lab_alert["label"]

        # Audit logs were generated
        assert AuditLog.objects.filter(action=AuditLog.Action.CREATE_LAB_RESULT).exists()
        assert AuditLog.objects.filter(action=AuditLog.Action.CREATE_ALERT).exists()


class TestClinicalCodeValidationAndIdempotency:
    def test_icd10_validation(self, client_as_doctor_a, encounter_a):
        # Invalid ICD-10 code rejected with 400
        resp = client_as_doctor_a.post(
            f"/api/encounters/{encounter_a.pk}/diagnoses/",
            json.dumps({"icd_code": "INVALID$$$", "description": "Test pneumonia"}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "icd_code" in resp.json()

        # Valid ICD-10 code accepted
        resp_valid = client_as_doctor_a.post(
            f"/api/encounters/{encounter_a.pk}/diagnoses/",
            json.dumps({"icd_code": "J18.9", "description": "Pneumonia, unspecified"}),
            content_type="application/json",
        )
        assert resp_valid.status_code == 201

    def test_snomed_validation(self, client_as_doctor_a, encounter_a):
        # Invalid SNOMED code rejected
        resp = client_as_doctor_a.post(
            f"/api/encounters/{encounter_a.pk}/diagnoses/",
            json.dumps({"snomed_code": "123", "description": "Short code"}),
            content_type="application/json",
        )
        assert resp.status_code == 400

        # Valid SNOMED code accepted
        resp_valid = client_as_doctor_a.post(
            f"/api/encounters/{encounter_a.pk}/diagnoses/",
            json.dumps({"snomed_code": "233604007", "description": "Pneumonia"}),
            content_type="application/json",
        )
        assert resp_valid.status_code == 201

    def test_rxnorm_validation(self, client_as_doctor_a, encounter_a):
        # Invalid RxNorm code rejected
        resp = client_as_doctor_a.post(
            f"/api/encounters/{encounter_a.pk}/prescriptions/",
            json.dumps(
                {
                    "drug_name": "Amoxicillin",
                    "dosage": "500mg",
                    "frequency": "TID",
                    "rxnorm_code": "INVALID",
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 400

        # Valid RxNorm code accepted
        resp_valid = client_as_doctor_a.post(
            f"/api/encounters/{encounter_a.pk}/prescriptions/",
            json.dumps(
                {
                    "drug_name": "Amoxicillin",
                    "dosage": "500mg",
                    "frequency": "TID",
                    "rxnorm_code": "723",
                }
            ),
            content_type="application/json",
        )
        assert resp_valid.status_code == 201

    def test_loinc_validation(self, client_as_doctor_a, patient_a):
        # Invalid LOINC code rejected
        resp = client_as_doctor_a.post(
            f"/api/patients/{patient_a.universal_id}/lab-orders/",
            json.dumps({"test_name": "CBC", "loinc_code": "NO_HYPHEN"}),
            content_type="application/json",
        )
        assert resp.status_code == 400

        # Valid LOINC code accepted
        resp_valid = client_as_doctor_a.post(
            f"/api/patients/{patient_a.universal_id}/lab-orders/",
            json.dumps({"test_name": "CBC", "loinc_code": "58410-2"}),
            content_type="application/json",
        )
        assert resp_valid.status_code == 201

    def test_prescription_idempotency_protection(self, client_as_doctor_a, encounter_a):
        headers = {"HTTP_IDEMPOTENCY_KEY": "test-idem-rx-1001"}
        payload = json.dumps(
            {
                "drug_name": "Paracetamol",
                "dosage": "500mg",
                "frequency": "QDS",
            }
        )

        # First submit
        r1 = client_as_doctor_a.post(
            f"/api/encounters/{encounter_a.pk}/prescriptions/",
            payload,
            content_type="application/json",
            **headers,
        )
        assert r1.status_code == 201

        # Second submit (double click)
        r2 = client_as_doctor_a.post(
            f"/api/encounters/{encounter_a.pk}/prescriptions/",
            payload,
            content_type="application/json",
            **headers,
        )
        assert r2.status_code == 201
        assert r2.json() == r1.json()

        # Verify ONLY one Prescription record exists in DB
        rxs = Prescription.objects.filter(encounter=encounter_a)
        assert rxs.count() == 1
        assert rxs.first().drug_name == "Paracetamol"

    def test_lab_order_idempotency_protection(self, client_as_doctor_a, patient_a):
        headers = {"HTTP_IDEMPOTENCY_KEY": "test-idem-lab-2002"}
        payload = json.dumps({"test_name": "Urinalysis", "priority": "urgent"})

        r1 = client_as_doctor_a.post(
            f"/api/patients/{patient_a.universal_id}/lab-orders/",
            payload,
            content_type="application/json",
            **headers,
        )
        assert r1.status_code == 201

        r2 = client_as_doctor_a.post(
            f"/api/patients/{patient_a.universal_id}/lab-orders/",
            payload,
            content_type="application/json",
            **headers,
        )
        assert r2.status_code == 201
        assert r2.json() == r1.json()

        from core.blind_index import make_blind_index
        from records.models import LabOrder

        assert (
            LabOrder.objects.filter(
                patient=patient_a, test_name_hash=make_blind_index("Urinalysis")
            ).count()
            == 1
        )
        assert LabOrder.objects.filter(patient=patient_a).first().test_name == "Urinalysis"

    def test_prescription_idempotency_different_body_creates_distinct_records(
        self, client_as_doctor_a, encounter_a
    ):
        # Same idempotency key used with DIFFERENT payloads
        headers = {"HTTP_IDEMPOTENCY_KEY": "test-idem-rx-diff-body"}
        p1 = json.dumps({"drug_name": "Paracetamol", "dosage": "500mg", "frequency": "QDS"})
        p2 = json.dumps({"drug_name": "Ibuprofen", "dosage": "400mg", "frequency": "TID"})

        r1 = client_as_doctor_a.post(
            f"/api/encounters/{encounter_a.pk}/prescriptions/",
            p1,
            content_type="application/json",
            **headers,
        )
        assert r1.status_code == 201
        assert r1.json()["drug_name"] == "Paracetamol"

        # Second request with same key but different body must NOT replay first response
        r2 = client_as_doctor_a.post(
            f"/api/encounters/{encounter_a.pk}/prescriptions/",
            p2,
            content_type="application/json",
            **headers,
        )
        assert r2.status_code == 201
        assert r2.json()["drug_name"] == "Ibuprofen"

        # Verify BOTH prescriptions were created in DB
        rxs = Prescription.objects.filter(encounter=encounter_a)
        assert rxs.count() == 2
        drug_names = {rx.drug_name for rx in rxs}
        assert drug_names == {"Paracetamol", "Ibuprofen"}

    def test_prescription_idempotency_in_flight_returns_409(
        self, client_as_doctor_a, encounter_a, doctor_a
    ):
        from django.core.cache import cache

        from api.idempotency import get_idempotency_key

        headers = {"HTTP_IDEMPOTENCY_KEY": "test-idem-rx-inflight"}
        payload = json.dumps({"drug_name": "Metformin", "dosage": "500mg", "frequency": "BD"})

        from rest_framework.test import APIRequestFactory

        factory = APIRequestFactory()
        req = factory.post(
            f"/api/encounters/{encounter_a.pk}/prescriptions/",
            data={"drug_name": "Metformin", "dosage": "500mg", "frequency": "BD"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="test-idem-rx-inflight",
        )
        req.user = doctor_a
        cache_key = get_idempotency_key(req, scope="create_prescription")
        cache.set(cache_key, "in-flight", timeout=60)

        # Now attempting to post should receive 409 Conflict
        r = client_as_doctor_a.post(
            f"/api/encounters/{encounter_a.pk}/prescriptions/",
            payload,
            content_type="application/json",
            **headers,
        )
        assert r.status_code == 409
        assert "in progress" in r.json()["detail"]

        # Ensure no prescription was created
        rxs = [rx.drug_name for rx in Prescription.objects.filter(encounter=encounter_a)]
        assert "Metformin" not in rxs

        # Release reservation
        cache.delete(cache_key)

    def test_prescription_idempotency_key_ordering_insensitivity(
        self, client_as_doctor_a, encounter_a
    ):
        headers = {"HTTP_IDEMPOTENCY_KEY": "test-idem-rx-key-order"}
        # Different key orders in json
        p1 = '{"dosage":"250mg","drug_name":"Cefalexin","frequency":"TID"}'
        p2 = '{"drug_name":"Cefalexin","frequency":"TID","dosage":"250mg"}'

        r1 = client_as_doctor_a.post(
            f"/api/encounters/{encounter_a.pk}/prescriptions/",
            p1,
            content_type="application/json",
            **headers,
        )
        assert r1.status_code == 201

        r2 = client_as_doctor_a.post(
            f"/api/encounters/{encounter_a.pk}/prescriptions/",
            p2,
            content_type="application/json",
            **headers,
        )
        assert r2.status_code == 201
        assert r2.json() == r1.json()

        # Only one prescription created
        rxs = [rx.drug_name for rx in Prescription.objects.filter(encounter=encounter_a)]
        assert rxs.count("Cefalexin") == 1

    def test_list_pagination_schema(self, client_as_doctor_a, patient_a):
        resp = client_as_doctor_a.get(f"/api/patients/{patient_a.universal_id}/encounters/")
        assert resp.status_code == 200
        data = resp.json()
        assert "count" in data
        assert "results" in data


class TestEncounterCascadeProtection:
    def test_encounter_delete_protected_when_diagnosis_exists(self, db, encounter_a, doctor_a):
        from django.db.models import ProtectedError
        from records.models import Diagnosis

        Diagnosis.objects.create(
            encounter=encounter_a,
            icd_code="J18.9",
            description="Pneumonia, unspecified",
            created_by=doctor_a,
        )

        with pytest.raises(ProtectedError):
            encounter_a.delete()

