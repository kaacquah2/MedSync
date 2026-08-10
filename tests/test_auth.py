"""
Tests for authentication, password change, and MFA flows via the REST API.

All tests use /api/* endpoints (session + CSRF) instead of the retired
Django template views.
"""

import json

from django.test import override_settings


class TestLogin:
    def test_login_success(self, db, doctor_a, client):
        resp = client.post(
            "/api/auth/login/",
            json.dumps({"username": doctor_a.username, "password": "Test@password1"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == doctor_a.username

    def test_login_wrong_password(self, db, doctor_a, client):
        resp = client.post(
            "/api/auth/login/",
            json.dumps({"username": doctor_a.username, "password": "wrongpassword"}),
            content_type="application/json",
        )
        assert resp.status_code == 401
        assert "error" in resp.json()

    def test_login_redirect_to_dashboard(self, db, doctor_a, client):
        resp = client.post(
            "/api/auth/login/",
            json.dumps({"username": doctor_a.username, "password": "Test@password1"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.json()["role"] == "doctor"


class TestPasswordChange:
    def test_password_change_success(self, db, doctor_a, client):
        client.force_login(doctor_a)
        resp = client.post(
            "/api/auth/password/change/",
            json.dumps({"old_password": "Test@password1", "new_password": "NewStrongPass@2024"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        doctor_a.refresh_from_db()
        assert doctor_a.check_password("NewStrongPass@2024")

    def test_password_change_wrong_old_password(self, client_as_doctor_a):
        resp = client_as_doctor_a.post(
            "/api/auth/password/change/",
            json.dumps({"old_password": "wrongpassword", "new_password": "NewStrongPass@2024"}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        from audit.models import AuditLog

        assert not AuditLog.objects.filter(action="PASSWORD_CHANGE").exists()

    def test_password_change_creates_audit_entry(self, db, doctor_a, client):
        from audit.models import AuditLog

        client.force_login(doctor_a)
        client.post(
            "/api/auth/password/change/",
            json.dumps({"old_password": "Test@password1", "new_password": "NewStrongPass@2024"}),
            content_type="application/json",
        )
        assert AuditLog.objects.filter(action="PASSWORD_CHANGE").exists()


class TestMFASetup:
    def test_mfa_setup_returns_qr_info(self, client_as_doctor_a):
        resp = client_as_doctor_a.get("/api/mfa/setup/")
        assert resp.status_code == 200
        data = resp.json()
        assert "qr_code" in data or "uri" in data or "secret" in data

    def test_mfa_setup_creates_device(self, db, doctor_a, client):
        from django_otp.plugins.otp_totp.models import TOTPDevice

        client.force_login(doctor_a)
        client.get("/api/mfa/setup/")
        assert TOTPDevice.objects.filter(user=doctor_a).exists()

    def test_mfa_setup_correct_code_confirms_device(self, db, doctor_a, client):
        import hashlib
        import hmac as _hmac
        import struct
        import time

        from django_otp.plugins.otp_totp.models import TOTPDevice

        client.force_login(doctor_a)
        device = TOTPDevice.objects.create(user=doctor_a, name="test", confirmed=False)
        raw_key = bytes.fromhex(device.key)
        t = int(time.time()) // device.step
        msg = struct.pack(">Q", t)
        h = _hmac.new(raw_key, msg, hashlib.sha1).digest()
        offset = h[-1] & 0x0F
        code = (struct.unpack(">I", h[offset : offset + 4])[0] & 0x7FFFFFFF) % (10**device.digits)
        code_str = str(code).zfill(device.digits)
        client.post(
            "/api/mfa/setup/",
            json.dumps({"code": code_str}),
            content_type="application/json",
        )
        device.refresh_from_db()
        assert device.confirmed is True

    def test_mfa_setup_wrong_code_does_not_confirm(self, db, doctor_a, client):
        from django_otp.plugins.otp_totp.models import TOTPDevice

        client.force_login(doctor_a)
        device = TOTPDevice.objects.create(user=doctor_a, name="test", confirmed=False)
        client.post(
            "/api/mfa/setup/",
            json.dumps({"code": "000000"}),
            content_type="application/json",
        )
        device.refresh_from_db()
        assert device.confirmed is False


class TestMFAEnforcement:
    @override_settings(MFA_ENFORCED=True)
    def test_mfa_required_role_returns_json_403_without_device(self, db, doctor_a, client):
        """
        When MFA_ENFORCED=True, a DOCTOR accessing /api/* without a device gets
        a JSON 403 {mfa_required: true, redirect: /spa/mfa/setup} — NOT a 302.
        The SPA axios interceptor reads this and navigates client-side.
        """
        client.force_login(doctor_a)
        resp = client.get("/api/dashboard/", follow=False)
        assert resp.status_code == 403
        data = resp.json()
        assert data["mfa_required"] is True
        assert "/spa/mfa/setup" in data["redirect"]

    @override_settings(MFA_ENFORCED=True)
    def test_mfa_required_role_returns_json_403_device_present_but_unverified(
        self, db, doctor_a, client
    ):
        """
        A DOCTOR with a confirmed device but without otp_verified in the session
        gets a JSON 403 directing to /spa/mfa/verify.
        """
        from django_otp.plugins.otp_totp.models import TOTPDevice

        TOTPDevice.objects.create(user=doctor_a, name="test", confirmed=True)
        client.force_login(doctor_a)
        # No session["otp_verified"] set → should block
        resp = client.get("/api/dashboard/", follow=False)
        assert resp.status_code == 403
        data = resp.json()
        assert data["mfa_required"] is True
        assert "/spa/mfa/verify" in data["redirect"]

    @override_settings(MFA_ENFORCED=True)
    def test_receptionist_not_blocked_by_mfa(self, db, receptionist_a, client):
        """RECEPTIONIST is not in MFA_REQUIRED_ROLES and reaches the endpoint normally."""
        client.force_login(receptionist_a)
        resp = client.get("/api/dashboard/", follow=False)
        # Should not be an MFA block (200 OK or non-MFA 403)
        assert resp.status_code != 403 or not resp.json().get("mfa_required")

    @override_settings(MFA_ENFORCED=False)
    def test_mfa_not_enforced_allows_clinical_access(self, db, doctor_a, client):
        """When MFA_ENFORCED=False, clinical users access dashboard freely."""
        client.force_login(doctor_a)
        resp = client.get("/api/dashboard/", follow=False)
        # Must not trigger MFA block
        if resp.status_code == 403:
            assert not resp.json().get("mfa_required")


class TestPasswordValidators:
    def test_numeric_password_rejected(self, db, doctor_a, client):
        """A numeric-only password is rejected by NumericPasswordValidator."""
        from django.test import override_settings

        validators = [
            {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
        ]
        client.force_login(doctor_a)
        with override_settings(AUTH_PASSWORD_VALIDATORS=validators):
            resp = client.post(
                "/api/auth/password/change/",
                '{"old_password": "Test@password1", "new_password": "123456789012"}',
                content_type="application/json",
            )
        assert resp.status_code == 400
        assert "error" in resp.json()

    def test_strong_password_accepted(self, db, doctor_a, client):
        """A strong, non-common password is accepted."""
        client.force_login(doctor_a)
        resp = client.post(
            "/api/auth/password/change/",
            '{"old_password": "Test@password1", "new_password": "Xk9#mP2vQr!nZ7wY"}',
            content_type="application/json",
        )
        assert resp.status_code == 200


class TestSessionInterruptedGraceful:
    @override_settings(SESSION_SAVE_EVERY_REQUEST=True)
    def test_session_interrupted_returns_400_for_api_route(self, db, doctor_a, client):
        """
        If a session update fails (raising UpdateError/SessionInterrupted),
        the SessionInterruptedMiddleware should catch it and return a clean 400 JSON response.
        """
        client.force_login(doctor_a)
        from unittest.mock import patch

        from django.contrib.sessions.backends.base import UpdateError

        # Patching SessionStore.save to simulate a concurrent logout / missing row on update
        with patch("django.contrib.sessions.backends.db.SessionStore.save") as mock_save:
            mock_save.side_effect = UpdateError

            resp = client.get("/api/me/")

            assert resp.status_code == 400
            assert resp.json() == {
                "error": "Session interrupted. The session was deleted concurrently."
            }

    @override_settings(SESSION_SAVE_EVERY_REQUEST=True)
    def test_session_interrupted_returns_400_for_non_api_route(self, db, doctor_a, client):
        """
        For a non-API route, it should return a clean plain-text 400 response.
        """
        client.force_login(doctor_a)
        from unittest.mock import patch

        from django.contrib.sessions.backends.base import UpdateError

        with patch("django.contrib.sessions.backends.db.SessionStore.save") as mock_save:
            mock_save.side_effect = UpdateError

            resp = client.get("/")

            assert resp.status_code == 400
            assert b"Session interrupted" in resp.content
            assert resp.headers["content-type"] == "text/plain"
