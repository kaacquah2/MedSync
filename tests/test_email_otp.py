"""
Tests for Email OTP generation, delivery, and verification flows.
"""

import json
from unittest.mock import patch
from django.core import mail
from django.test import override_settings
from accounts.models import EmailOTP, User


class TestEmailOTP:
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
    def test_send_email_otp_missing_email_rejected(self, db, doctor_a, client):
        doctor_a.email = ""
        doctor_a.save()
        client.force_login(doctor_a)

        resp = client.post("/api/mfa/send-email-otp/")
        assert resp.status_code == 400
        assert "No email address" in resp.json()["error"]

    @override_settings(MFA_ENFORCED=True)
    def test_verify_email_otp_success(self, db, doctor_a, client):
        doctor_a.email = "doctor@hospital.org"
        doctor_a.save()

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
