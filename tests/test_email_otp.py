"""
Tests for Email OTP generation, delivery, and verification flows.
"""

import json

import pytest
from django.core import mail
from django.test import override_settings
from django_otp.plugins.otp_totp.models import TOTPDevice

from accounts.models import EmailOTP
from audit.models import AuditLog


class TestEmailOTP:
    @pytest.fixture(autouse=True)
    def clear_throttle_cache(self):
        from django.core.cache import cache

        cache.clear()
        yield
        cache.clear()

    @override_settings(MFA_ENFORCED=True)
    def test_send_email_otp_success(self, db, doctor_a, client):
        doctor_a.email = "doctor@hospital.org"
        doctor_a.save()
        client.force_login(doctor_a)

        resp = client.post("/api/mfa/send-email-otp/")
        assert resp.status_code == 200
        data = resp.json()
        assert "sent" in data["detail"]
        assert "d***r@hospital.org" in data["email_masked"]

        # Verify email was dispatched
        assert len(mail.outbox) == 1
        sent_mail = mail.outbox[0]
        assert "Your mEd Verification Code" in sent_mail.subject
        assert "doctor@hospital.org" in sent_mail.to

        # Verify EmailOTP record created in DB
        assert EmailOTP.objects.filter(user=doctor_a, used=False).exists()

    @override_settings(MFA_ENFORCED=True)
    def test_send_email_otp_audit_log_choice_and_masked_pii(self, db, doctor_a, client):
        doctor_a.email = "doctor@hospital.org"
        doctor_a.save()
        client.force_login(doctor_a)

        resp = client.post("/api/mfa/send-email-otp/")
        assert resp.status_code == 200

        # Verify audit log recorded with registered action choice
        log = AuditLog.objects.filter(actor=doctor_a, action=AuditLog.Action.EMAIL_OTP_SENT).latest(
            "timestamp"
        )
        assert log.action == "EMAIL_OTP_SENT"
        assert log.get_action_display() == "Email OTP Sent"

        # Verify staff email PII is masked in audit log extra
        assert log.extra.get("email") == "d***r@hospital.org"
        assert "doctor@hospital.org" != log.extra.get("email")

    @override_settings(MFA_ENFORCED=True)
    def test_send_email_otp_missing_email_rejected(self, db, doctor_a, client):
        doctor_a.email = ""
        doctor_a.save()
        client.force_login(doctor_a)

        resp = client.post("/api/mfa/send-email-otp/")
        assert resp.status_code == 400
        assert "No email address" in resp.json()["error"]

    @override_settings(MFA_ENFORCED=True)
    def test_verify_email_otp_rejected_without_totp_device(self, db, doctor_a, client):
        """
        Email OTP cannot be used as a standalone second factor to bypass
        TOTP device setup if no confirmed TOTP device exists.
        """
        doctor_a.email = "doctor@hospital.org"
        doctor_a.save()
        otp_code = EmailOTP.objects.generate_for(doctor_a)

        client.force_login(doctor_a)
        resp = client.post(
            "/api/mfa/verify/",
            json.dumps({"code": otp_code}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "Invalid code" in resp.json()["error"]
        assert client.session.get("otp_verified") is not True

    @override_settings(MFA_ENFORCED=True)
    def test_verify_email_otp_success(self, db, doctor_a, client):
        doctor_a.email = "doctor@hospital.org"
        doctor_a.save()
        TOTPDevice.objects.create(user=doctor_a, name="default", confirmed=True)

        # Generate OTP
        otp_code = EmailOTP.objects.generate_for(doctor_a)
        assert len(otp_code) == 6

        client.force_login(doctor_a)
        resp = client.post(
            "/api/mfa/verify/",
            json.dumps({"code": otp_code}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert "verified" in resp.json()["detail"].lower()

        # Check session verified
        session = client.session
        assert session.get("otp_verified") is True

        # Check OTP consumed (used=True)
        otp_record = EmailOTP.objects.filter(user=doctor_a).first()
        assert otp_record.used is True

    @override_settings(MFA_ENFORCED=True)
    def test_verify_email_otp_invalid_code_rejected(self, db, doctor_a, client):
        doctor_a.email = "doctor@hospital.org"
        doctor_a.save()
        TOTPDevice.objects.create(user=doctor_a, name="default", confirmed=True)
        EmailOTP.objects.generate_for(doctor_a)

        client.force_login(doctor_a)
        resp = client.post(
            "/api/mfa/verify/",
            json.dumps({"code": "999999"}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "Invalid code" in resp.json()["error"]

    @override_settings(MFA_ENFORCED=True)
    def test_verify_email_otp_single_use(self, db, doctor_a, client):
        doctor_a.email = "doctor@hospital.org"
        doctor_a.save()
        TOTPDevice.objects.create(user=doctor_a, name="default", confirmed=True)
        otp_code = EmailOTP.objects.generate_for(doctor_a)

        client.force_login(doctor_a)
        # First verification succeeds
        resp1 = client.post(
            "/api/mfa/verify/",
            json.dumps({"code": otp_code}),
            content_type="application/json",
        )
        assert resp1.status_code == 200

        # Reset session flag to test second attempt
        session = client.session
        session["otp_verified"] = False
        session.save()

        # Second verification with same code fails
        resp2 = client.post(
            "/api/mfa/verify/",
            json.dumps({"code": otp_code}),
            content_type="application/json",
        )
        assert resp2.status_code == 400

    @override_settings(MFA_ENFORCED=True)
    def test_email_otp_burned_after_five_failed_attempts(self, db, doctor_a, client):
        """
        After 5 failed attempts, the Email OTP is invalidated (burned),
        and subsequent attempts even with the correct code are rejected.
        """
        from django.core.cache import cache

        cache.clear()

        doctor_a.email = "doctor@hospital.org"
        doctor_a.save()
        TOTPDevice.objects.create(user=doctor_a, name="default", confirmed=True)
        otp_code = EmailOTP.objects.generate_for(doctor_a)

        client.force_login(doctor_a)

        # 4 failed attempts
        for i in range(1, 5):
            cache.clear()
            resp = client.post(
                "/api/mfa/verify/",
                json.dumps({"code": f"00000{i}"}),
                content_type="application/json",
            )
            assert resp.status_code == 400
            otp_record = EmailOTP.objects.get(user=doctor_a)
            assert otp_record.attempts == i
            assert otp_record.used is False

        # 5th failed attempt: burns the OTP
        cache.clear()
        resp5 = client.post(
            "/api/mfa/verify/",
            json.dumps({"code": "000005"}),
            content_type="application/json",
        )
        assert resp5.status_code == 400
        otp_record = EmailOTP.objects.get(user=doctor_a)
        assert otp_record.attempts == 5
        assert otp_record.used is True

        # Now try the correct code: should still be rejected because OTP is burned
        cache.clear()
        resp_correct = client.post(
            "/api/mfa/verify/",
            json.dumps({"code": otp_code}),
            content_type="application/json",
        )
        assert resp_correct.status_code == 400
        assert client.session.get("otp_verified") is not True

    def test_email_otp_uses_keyed_hmac_and_rejects_bare_sha256(self, db, doctor_a):
        import hashlib

        from accounts.models import hash_email_otp

        otp_code = EmailOTP.objects.generate_for(doctor_a)
        otp_record = EmailOTP.objects.get(user=doctor_a)

        expected_hmac = hash_email_otp(otp_code)
        bare_sha256 = hashlib.sha256(otp_code.encode()).hexdigest()

        assert otp_record.code_hash == expected_hmac
        assert otp_record.code_hash != bare_sha256
        assert len(otp_record.code_hash) == 64

    def test_email_otp_legacy_sha256_fallback(self, db, doctor_a):
        import hashlib

        from django.utils import timezone

        legacy_code = "123456"
        legacy_hash = hashlib.sha256(legacy_code.encode()).hexdigest()
        expires_at = timezone.now() + timezone.timedelta(minutes=10)

        EmailOTP.objects.create(
            user=doctor_a,
            code_hash=legacy_hash,
            expires_at=expires_at,
            attempts=0,
        )

        assert EmailOTP.objects.verify_and_consume(doctor_a, legacy_code) is True
        consumed = EmailOTP.objects.get(user=doctor_a)
        assert consumed.used is True
