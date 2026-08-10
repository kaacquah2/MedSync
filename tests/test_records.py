"""
Tests for the clinical records (Encounter, Diagnosis, Prescription, LabResult).

Verifies:
  - Encounter creation via API stamps created_by and created_at_hospital
  - Encrypted fields (chief_complaint, drug_name) stored as ciphertext in DB
  - Prescription creation restricted to DOCTOR role
  - Lab result creation allowed for LAB_TECH, DOCTOR, NURSE
"""

import json

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

    def test_nurse_can_add_diagnosis(self, db, nurse_a, encounter_a, client):
        client.force_login(nurse_a)
        resp = client.post(
            f"/api/encounters/{encounter_a.pk}/diagnoses/",
            json.dumps({"icd_code": "R51.9", "description": "Headache", "is_primary": True}),
            content_type="application/json",
        )
        assert resp.status_code == 201


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
            json.dumps({
                "drug_name": "Amoxicillin",
                "dosage": "500mg",
                "frequency": "TID",
                "rxnorm_code": "INVALID",
            }),
            content_type="application/json",
        )
        assert resp.status_code == 400

        # Valid RxNorm code accepted
        resp_valid = client_as_doctor_a.post(
            f"/api/encounters/{encounter_a.pk}/prescriptions/",
            json.dumps({
                "drug_name": "Amoxicillin",
                "dosage": "500mg",
                "frequency": "TID",
                "rxnorm_code": "723",
            }),
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
        payload = json.dumps({
            "drug_name": "Paracetamol",
            "dosage": "500mg",
            "frequency": "QDS",
        })

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

        from records.models import LabOrder
        assert LabOrder.objects.filter(patient=patient_a, test_name="Urinalysis").count() == 1

    def test_list_pagination_schema(self, client_as_doctor_a, patient_a):
        resp = client_as_doctor_a.get(f"/api/patients/{patient_a.universal_id}/encounters/")
        assert resp.status_code == 200
        data = resp.json()
        assert "count" in data
        assert "results" in data

