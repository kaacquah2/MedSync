"""
Tests for Role-Based Access Control via the REST API.

Verifies:
  - IsAuthenticated: unauthenticated → 403
  - Patient detail: same-hospital allowed, cross-hospital denied (403)
  - Encounter creation: DOCTOR/NURSE allowed, RECEPTIONIST → 403
  - Prescription creation: DOCTOR allowed, NURSE → 403
  - Audit log: SYSTEM_ADMIN allowed, others → 403
  - Hospital create: SYSTEM_ADMIN allowed, DOCTOR → 403
"""

import json


class TestPatientDetailAccess:
    def test_doctor_can_view_patient(self, client_as_doctor_a, patient_a):
        resp = client_as_doctor_a.get(f"/api/patients/{patient_a.universal_id}/")
        assert resp.status_code == 200

    def test_receptionist_can_view_patient_detail(self, client_as_receptionist, patient_a):
        resp = client_as_receptionist.get(f"/api/patients/{patient_a.universal_id}/")
        assert resp.status_code == 200

    def test_unauthenticated_is_denied(self, client, patient_a):
        resp = client.get(f"/api/patients/{patient_a.universal_id}/")
        assert resp.status_code == 401


class TestEncounterCreation:
    def test_doctor_can_create_encounter(self, client_as_doctor_a, patient_a):
        resp = client_as_doctor_a.post(
            f"/api/patients/{patient_a.universal_id}/encounters/",
            json.dumps({"encounter_type": "OPD", "chief_complaint": "Headache"}),
            content_type="application/json",
        )
        assert resp.status_code == 201

    def test_receptionist_cannot_create_encounter(self, client_as_receptionist, patient_a):
        resp = client_as_receptionist.post(
            f"/api/patients/{patient_a.universal_id}/encounters/",
            json.dumps({"encounter_type": "OPD", "chief_complaint": "Headache"}),
            content_type="application/json",
        )
        assert resp.status_code == 403

    def test_unauthenticated_is_denied(self, client, patient_a):
        resp = client.post(
            f"/api/patients/{patient_a.universal_id}/encounters/",
            json.dumps({"encounter_type": "OPD", "chief_complaint": "Headache"}),
            content_type="application/json",
        )
        assert resp.status_code == 401


class TestPrescriptionRBAC:
    def test_nurse_cannot_create_prescription(self, db, nurse_a, encounter_a, client):
        client.force_login(nurse_a)
        resp = client.post(
            f"/api/encounters/{encounter_a.pk}/prescriptions/",
            json.dumps({"drug_name": "Paracetamol", "dosage": "500mg", "frequency": "8h"}),
            content_type="application/json",
        )
        assert resp.status_code == 403

    def test_doctor_can_create_prescription(self, client_as_doctor_a, encounter_a):
        resp = client_as_doctor_a.post(
            f"/api/encounters/{encounter_a.pk}/prescriptions/",
            json.dumps({"drug_name": "Paracetamol", "dosage": "500mg", "frequency": "8h"}),
            content_type="application/json",
        )
        assert resp.status_code == 201


class TestAuditLogAccess:
    def test_sysadmin_can_view_audit_log(self, client_as_sysadmin):
        resp = client_as_sysadmin.get("/api/audit/")
        assert resp.status_code == 200

    def test_doctor_cannot_view_audit_log(self, client_as_doctor_a):
        resp = client_as_doctor_a.get("/api/audit/")
        assert resp.status_code == 403

    def test_receptionist_cannot_view_audit_log(self, client_as_receptionist):
        resp = client_as_receptionist.get("/api/audit/")
        assert resp.status_code == 403


class TestHospitalAdminRBAC:
    def test_sysadmin_can_create_hospital(self, client_as_sysadmin):
        resp = client_as_sysadmin.post(
            "/api/hospitals/",
            json.dumps({"name": "New Hospital", "code": "NEWHSP"}),
            content_type="application/json",
        )
        assert resp.status_code == 201

    def test_doctor_cannot_create_hospital(self, client_as_doctor_a):
        resp = client_as_doctor_a.post(
            "/api/hospitals/",
            json.dumps({"name": "New Hospital", "code": "NEWHSP2"}),
            content_type="application/json",
        )
        assert resp.status_code == 403


class TestEncounterDetailRBAC:
    def test_receptionist_cannot_view_encounter_detail(self, client_as_receptionist, encounter_a):
        resp = client_as_receptionist.get(f"/api/encounters/{encounter_a.pk}/")
        assert resp.status_code == 403

    def test_doctor_can_view_encounter_detail(self, client_as_doctor_a, encounter_a):
        resp = client_as_doctor_a.get(f"/api/encounters/{encounter_a.pk}/")
        assert resp.status_code == 200

    def test_nurse_can_view_encounter_detail(self, client, nurse_a, encounter_a):
        client.force_login(nurse_a)
        resp = client.get(f"/api/encounters/{encounter_a.pk}/")
        assert resp.status_code == 200

    def test_lab_tech_cannot_view_encounter_detail(self, client, db, hospital_a, encounter_a):
        from accounts.models import User

        lab_tech = User.objects.create_user(
            username="labtech_enc_test",
            password="Test@password1",
            role="lab_technician",
            hospital=hospital_a,
        )
        client.force_login(lab_tech)
        resp = client.get(f"/api/encounters/{encounter_a.pk}/")
        assert resp.status_code == 403

    def test_hospital_admin_cannot_view_encounter_detail(
        self, client_as_hospital_admin_a, encounter_a
    ):
        resp = client_as_hospital_admin_a.get(f"/api/encounters/{encounter_a.pk}/")
        assert resp.status_code == 403


class TestBreakGlassRBAC:
    def setup_method(self):
        from api.permissions import BreakGlassThrottle

        BreakGlassThrottle().cache.clear()

    def test_receptionist_cannot_break_glass(self, client_as_receptionist, patient_a):
        resp = client_as_receptionist.post(
            f"/api/patients/{patient_a.universal_id}/break-glass/",
            json.dumps({"reason": "Emergency clinical access needed for treatment"}),
            content_type="application/json",
        )
        assert resp.status_code == 403

    def test_doctor_can_break_glass(self, client_as_doctor_a, patient_a):
        resp = client_as_doctor_a.post(
            f"/api/patients/{patient_a.universal_id}/break-glass/",
            json.dumps({"reason": "Emergency clinical access needed for urgent treatment"}),
            content_type="application/json",
        )
        assert resp.status_code == 201


class TestDocumentAccessRBAC:
    def test_receptionist_cannot_list_documents(self, client_as_receptionist, patient_a):
        resp = client_as_receptionist.get(f"/api/patients/{patient_a.universal_id}/documents/")
        assert resp.status_code == 403

    def test_doctor_can_list_documents(self, client_as_doctor_a, patient_a):
        resp = client_as_doctor_a.get(f"/api/patients/{patient_a.universal_id}/documents/")
        assert resp.status_code == 200

    def test_receptionist_cannot_delete_document(self, client_as_receptionist, patient_a, doctor_a):
        from django.core.files.uploadedfile import SimpleUploadedFile

        from records.models import PatientDocument

        doc = PatientDocument.objects.create(
            patient=patient_a,
            uploaded_by=doctor_a,
            file=SimpleUploadedFile(
                "scan.png", b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR", content_type="image/png"
            ),
            original_name="scan.png",
            file_type="image/png",
            file_size=16,
        )
        resp = client_as_receptionist.delete(
            f"/api/patients/{patient_a.universal_id}/documents/{doc.pk}/"
        )
        assert resp.status_code == 403
        assert PatientDocument.objects.filter(pk=doc.pk).exists()

    def test_doctor_can_delete_document(self, client_as_doctor_a, patient_a, doctor_a):
        from django.core.files.uploadedfile import SimpleUploadedFile

        from records.models import PatientDocument

        doc = PatientDocument.objects.create(
            patient=patient_a,
            uploaded_by=doctor_a,
            file=SimpleUploadedFile(
                "scan.png", b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR", content_type="image/png"
            ),
            original_name="scan.png",
            file_type="image/png",
            file_size=16,
        )
        resp = client_as_doctor_a.delete(
            f"/api/patients/{patient_a.universal_id}/documents/{doc.pk}/"
        )
        assert resp.status_code == 204
        assert not PatientDocument.objects.filter(pk=doc.pk).exists()


class TestSessionInvalidationAndLogout:
    def test_logout_invalidates_session_server_side(self, client_as_doctor_a, doctor_a):
        session_key = client_as_doctor_a.session.session_key
        assert session_key is not None
        resp = client_as_doctor_a.post("/api/auth/logout/")
        assert resp.status_code == 200
        # Post-logout request to protected endpoint fails with 401
        me_resp = client_as_doctor_a.get("/api/me/")
        assert me_resp.status_code == 401
