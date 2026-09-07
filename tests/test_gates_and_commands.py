from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.utils import timezone

from access.models import BreakGlassAccess, PatientConsent
from access.permissions import can_access_patient
from audit.models import AuditLog
from records.models import PatientDocument


class TestPatientConsentGating:
    def test_consent_hard_blocking(self, db, doctor_a, patient_a, hospital_a):
        # Same hospital default: allowed
        assert can_access_patient(doctor_a, patient_a).allowed is True

        # Explicitly revoked consent: denied
        PatientConsent.objects.create(
            patient=patient_a,
            hospital=hospital_a,
            granted=False,
            revoked_at=timezone.now(),
        )
        assert can_access_patient(doctor_a, patient_a).allowed is False

        # Break-glass bypasses revoked consent
        BreakGlassAccess.objects.create(
            actor=doctor_a,
            patient=patient_a,
            reason="Emergency bypass of consent block",
            expires_at=timezone.now() + timedelta(hours=1),
        )
        assert can_access_patient(doctor_a, patient_a).allowed is True


class TestDocumentUploadHardening:
    def test_upload_extension_allowlist(self, client_as_doctor_a, patient_a):
        # Disallowed extension (.exe)
        invalid_file = SimpleUploadedFile(
            "malware.exe", b"MZ\x90\x00\x03\x00\x00\x00", content_type="application/octet-stream"
        )
        resp = client_as_doctor_a.post(
            f"/api/patients/{patient_a.universal_id}/documents/",
            {"file": invalid_file, "description": "malware"},
        )
        assert resp.status_code == 400
        assert "is not allowed" in resp.json()["error"]

    def test_upload_mime_signature_sniffing(self, client_as_doctor_a, patient_a):
        # PNG extension but random text content (not matching PNG magic bytes)
        invalid_png = SimpleUploadedFile(
            "fake.png", b"not-a-png-file-content", content_type="image/png"
        )
        resp = client_as_doctor_a.post(
            f"/api/patients/{patient_a.universal_id}/documents/",
            {"file": invalid_png, "description": "fake image"},
        )
        assert resp.status_code == 400
        assert "signature mismatch" in resp.json()["error"]

    def test_document_encryption_and_decryption(self, client_as_doctor_a, patient_a):
        # Valid PNG with correct magic bytes
        png_content = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        valid_png = SimpleUploadedFile("image.png", png_content, content_type="image/png")

        # Upload
        resp = client_as_doctor_a.post(
            f"/api/patients/{patient_a.universal_id}/documents/",
            {"file": valid_png, "description": "secret xray image"},
        )
        assert resp.status_code == 201
        doc_id = resp.json()["id"]

        # Check raw bytes in DB/storage are indeed encrypted (starts with Fernet header gAAAAA)
        doc = PatientDocument.objects.get(pk=doc_id)
        with doc.file.open("rb") as f:
            stored_bytes = f.read()
        assert stored_bytes.startswith(b"gAAAAA")
        assert stored_bytes != png_content

        # Download / Decrypt
        dl_resp = client_as_doctor_a.get(
            f"/api/patients/{patient_a.universal_id}/documents/{doc_id}/download/"
        )
        assert dl_resp.status_code == 200
        downloaded_content = b"".join(dl_resp.streaming_content)
        assert downloaded_content == png_content


class TestPruneAuditLogsCommand:
    def test_pruning_command_deletes_old_logs(self, db):
        # Create an entry older than 30 days
        old_log = AuditLog.objects.create(
            actor_username="old_user",
            actor_role="doctor",
            actor_hospital="Hospital A",
            action="ACCESS_PATIENT",
            timestamp=timezone.now() - timedelta(days=35),
            prev_hash="",
            row_hash="xyz",
        )

        # Create a fresh entry
        new_log = AuditLog.objects.create(
            actor_username="new_user",
            actor_role="doctor",
            actor_hospital="Hospital A",
            action="ACCESS_PATIENT",
            timestamp=timezone.now(),
            prev_hash="xyz",
            row_hash="abc",
        )

        # Run command with --force to bypass stdin confirmation
        call_command("prune_audit_logs", days=30, force=True)

        # Verify old_log is deleted, new_log is kept
        assert not AuditLog.objects.filter(pk=old_log.pk).exists()
        assert AuditLog.objects.filter(pk=new_log.pk).exists()
