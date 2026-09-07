"""
Unit tests validating fixes for audit items:
- /healthz/ failure obscurity and logging
- RecoveryCode keyed HMAC and legacy SHA-256 fallback
- Patient date_of_birth validation
- Document upload MIME sniffing (DOCX OpenXML structure and TXT control chars)
- Document download decryption failure (500 error instead of raw ciphertext)
"""

import hashlib
import io
import zipfile
from datetime import date, timedelta
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.test import RequestFactory

from accounts.models import RecoveryCode, hash_recovery_code
from api.views.documents import sniff_file_mime
from emr.urls import healthz
from patients.models import validate_date_of_birth


@pytest.mark.django_db
class TestHealthzEndpoint:
    def test_healthz_ok(self):
        rf = RequestFactory()
        req = rf.get("/healthz/")
        resp = healthz(req)
        assert resp.status_code == 200
        data = resp.getvalue().decode()
        assert '"status": "ok"' in data
        assert '"database": "connected"' in data

    def test_healthz_db_failure_obscured(self):
        rf = RequestFactory()
        req = rf.get("/healthz/")
        with patch(
            "django.db.connection.ensure_connection",
            side_effect=Exception("FATAL: password authentication failed for user secret_user"),
        ):
            resp = healthz(req)
        assert resp.status_code == 503
        data = resp.getvalue().decode()
        assert data == '{"status": "error"}'
        assert "secret_user" not in data
        assert "password authentication failed" not in data


@pytest.mark.django_db
class TestRecoveryCodeHMAC:
    def test_hmac_generation_and_consumption(self, doctor_a):
        codes = RecoveryCode.objects.generate_for(doctor_a)
        assert len(codes) == 8
        test_code = codes[0]

        # Ensure stored hash matches keyed HMAC, not raw SHA-256
        expected_hmac = hash_recovery_code(test_code)
        raw_sha256 = hashlib.sha256(test_code.encode()).hexdigest()
        assert RecoveryCode.objects.filter(
            user=doctor_a, code_hash=expected_hmac, used=False
        ).exists()
        assert not RecoveryCode.objects.filter(user=doctor_a, code_hash=raw_sha256).exists()

        # Consuming works
        assert RecoveryCode.objects.verify_and_consume(doctor_a, test_code) is True
        # Cannot consume twice
        assert RecoveryCode.objects.verify_and_consume(doctor_a, test_code) is False

    def test_legacy_sha256_fallback(self, doctor_a):
        legacy_code = "LEGACY1234"
        legacy_hash = hashlib.sha256(legacy_code.encode()).hexdigest()
        RecoveryCode.objects.create(user=doctor_a, code_hash=legacy_hash, used=False)

        assert RecoveryCode.objects.verify_and_consume(doctor_a, legacy_code) is True
        rc = RecoveryCode.objects.get(user=doctor_a, code_hash=legacy_hash)
        assert rc.used is True


class TestDateOfBirthValidation:
    def test_valid_dates(self):
        validate_date_of_birth("1990-05-15")
        validate_date_of_birth("2000-01-01")
        validate_date_of_birth(date.today().isoformat())

    def test_invalid_format(self):
        with pytest.raises(ValidationError, match="YYYY-MM-DD format"):
            validate_date_of_birth("05/15/1990")
        with pytest.raises(ValidationError, match="YYYY-MM-DD format"):
            validate_date_of_birth("19900515")
        with pytest.raises(ValidationError, match="YYYY-MM-DD format"):
            validate_date_of_birth("invalid-date")

    def test_invalid_calendar_date(self):
        with pytest.raises(ValidationError, match="Invalid calendar date"):
            validate_date_of_birth("1990-02-31")
        with pytest.raises(ValidationError, match="Invalid calendar date"):
            validate_date_of_birth("1990-13-01")

    def test_future_date(self):
        future_date = (date.today() + timedelta(days=1)).isoformat()
        with pytest.raises(ValidationError, match="cannot be in the future"):
            validate_date_of_birth(future_date)


class TestDocumentMimeSniffing:
    def test_valid_docx_with_openxml_structure(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("[Content_Types].xml", b"<Types></Types>")
            zf.writestr("word/document.xml", b"<w:document></w:document>")
        docx_bytes = buf.getvalue()

        assert sniff_file_mime(docx_bytes[:512], file_obj=io.BytesIO(docx_bytes)) == (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

    def test_arbitrary_zip_rejected_as_docx(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("malicious.exe", b"MZ\x90\x00")
        zip_bytes = buf.getvalue()

        assert sniff_file_mime(zip_bytes[:512], file_obj=io.BytesIO(zip_bytes)) is None

    def test_valid_plaintext(self):
        valid_txt = b"Hello world! Clinical discharge summary notes.\nLine 2 with numbers 12345."
        assert sniff_file_mime(valid_txt) == "text/plain"

    def test_plaintext_with_control_chars_rejected(self):
        # Binary data with ASCII null or control chars like \x07 (bell) or \x00
        binary_txt = b"Hello\x00World\x07Binary"
        assert sniff_file_mime(binary_txt) is None


@pytest.mark.django_db
class TestDocumentDownloadDecryptionFailure:
    def test_decryption_failure_returns_500(self, client_as_doctor_a, doctor_a, patient_a):
        from django.core.files.base import ContentFile

        from records.models import PatientDocument

        # Create a document whose ciphertext is corrupted or cannot be decrypted
        corrupted_cipher = b"gAAAAABinvalidfernetciphertextpayload"
        doc = PatientDocument.objects.create(
            patient=patient_a,
            uploaded_by=doctor_a,
            file=ContentFile(corrupted_cipher, name="corrupted.pdf"),
            original_name="corrupted.pdf",
            file_type="application/pdf",
            file_size=len(corrupted_cipher),
        )

        url = f"/api/patients/{patient_a.universal_id}/documents/{doc.pk}/download/"
        resp = client_as_doctor_a.get(url)
        assert resp.status_code == 500
        data = resp.json()
        assert "Failed to decrypt document" in data["error"]
