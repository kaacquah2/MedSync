"""
MFA API views — TOTP setup, verify, disable, recovery codes, sign-out-all.

Reuses all the existing logic from accounts/views.py; just wraps it in
DRF APIView so the React SPA can drive the flow.
"""

import base64
import io

from django.contrib.sessions.models import Session
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from accounts.mfa_middleware import MFAEnforcementMiddleware
from audit.utils import log_action


class MfaSetupView(APIView):
    """
    GET  /api/mfa/setup/ — return QR code URI + secret for a new TOTP device.
    POST /api/mfa/setup/ — confirm with a TOTP code to activate the device.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "mfa_verify"

    def get(self, request):
        from django_otp.plugins.otp_totp.models import TOTPDevice

        # Create (or return existing unconfirmed) TOTP device
        device, _ = TOTPDevice.objects.get_or_create(
            user=request.user,
            confirmed=False,
            defaults={"name": "default"},
        )
        import qrcode as _qrcode

        uri = device.config_url
        qr_img = _qrcode.make(uri)
        buf = io.BytesIO()
        qr_img.save(buf)
        qr_b64 = base64.b64encode(buf.getvalue()).decode()

        return Response(
            {
                "qr_code": f"data:image/png;base64,{qr_b64}",
                "uri": uri,
                "secret": device.bin_key.hex() if hasattr(device, "bin_key") else "",
            }
        )

    def post(self, request):
        from django_otp.plugins.otp_totp.models import TOTPDevice

        code = request.data.get("code", "").strip()
        device = TOTPDevice.objects.filter(user=request.user, confirmed=False).first()
        if not device:
            return Response(
                {"error": "No pending TOTP device found. Please call GET /api/mfa/setup/ first."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not device.verify_token(code):
            return Response(
                {"error": "Invalid TOTP code. Please try again."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        device.confirmed = True
        device.save(update_fields=["confirmed"])
        request.session["otp_verified"] = True

        # Generate recovery codes
        from accounts.models import RecoveryCode

        codes = RecoveryCode.objects.generate_for(request.user)

        log_action(request, action="MFA_ENROLLED", extra={"via": "api"})

        return Response(
            {
                "detail": "MFA enabled successfully.",
                "recovery_codes": codes,
            },
            status=status.HTTP_201_CREATED,
        )


class SendEmailOtpView(APIView):
    """
    POST /api/mfa/send-email-otp/
    Generates a 6-digit Email OTP and emails it to the authenticated user.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "mfa_verify"

    def post(self, request):
        user = request.user
        email = (user.email or "").strip()

        if not email:
            return Response(
                {"error": "No email address registered for this account. Contact your admin."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from accounts.models import EmailOTP
        from django.core.mail import send_mail

        otp_code = EmailOTP.objects.generate_for(user)

        subject = "Your mEd Verification Code"
        message = (
            f"Hello {user.get_full_name() or user.username},\n\n"
            f"Your mEd verification code is: {otp_code}\n\n"
            f"This code will expire in 10 minutes. If you did not request this code, please contact IT security.\n"
        )

        send_mail(
            subject=subject,
            message=message,
            from_email=None,
            recipient_list=[email],
            fail_silently=False,
        )

        log_action(request, action="EMAIL_OTP_SENT", extra={"email": email, "via": "api"})

        parts = email.split("@")
        if len(parts) == 2 and len(parts[0]) > 2:
            masked = f"{parts[0][0]}***{parts[0][-1]}@{parts[1]}"
        else:
            masked = email

        return Response(
            {
                "detail": f"Verification code sent to {masked}.",
                "email_masked": masked,
            },
            status=status.HTTP_200_OK,
        )


class MfaVerifyView(APIView):
    """
    POST /api/mfa/verify/
    Body: { "code": "123456" }  (TOTP, Email OTP, or recovery code)

    Marks session["otp_verified"] = True and sets the trusted-device cookie.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "mfa_verify"

    def post(self, request):
        from django_otp.plugins.otp_totp.models import TOTPDevice

        from accounts.models import EmailOTP, RecoveryCode

        code = request.data.get("code", "").strip()

        confirmed_device = TOTPDevice.objects.filter(user=request.user, confirmed=True).first()

        # 1. Try TOTP device (if present)
        if confirmed_device and confirmed_device.verify_token(code):
            request.session["otp_verified"] = True
            log_action(request, action="MFA_VERIFIED", extra={"method": "totp", "via": "api"})
            response = Response({"detail": "MFA verified."})
            MFAEnforcementMiddleware.set_trusted_device_cookie(
                response, request.user, confirmed_device
            )
            return response

        # 2. Try Email OTP
        if EmailOTP.objects.verify_and_consume(request.user, code):
            request.session["otp_verified"] = True
            log_action(
                request, action="MFA_VERIFIED", extra={"method": "email_otp", "via": "api"}
            )
            response = Response({"detail": "MFA verified via email OTP."})
            if confirmed_device:
                MFAEnforcementMiddleware.set_trusted_device_cookie(
                    response, request.user, confirmed_device
                )
            return response

        # 3. Try recovery code
        if RecoveryCode.objects.verify_and_consume(request.user, code):
            request.session["otp_verified"] = True
            log_action(
                request, action="MFA_VERIFIED", extra={"method": "recovery_code", "via": "api"}
            )
            return Response({"detail": "MFA verified via recovery code."})

        return Response(
            {"error": "Invalid code. Please try again."},
            status=status.HTTP_400_BAD_REQUEST,
        )


class MfaDisableView(APIView):
    """
    POST /api/mfa/disable/
    Body: { "code": "123456" }  — must confirm with current TOTP code.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "mfa_verify"

    def post(self, request):
        from django_otp.plugins.otp_totp.models import TOTPDevice

        from accounts.models import RecoveryCode

        code = request.data.get("code", "").strip()
        device = TOTPDevice.objects.filter(user=request.user, confirmed=True).first()
        if not device:
            return Response(
                {"error": "MFA is not enabled for this account."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not device.verify_token(code):
            return Response(
                {"error": "Invalid TOTP code."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        device.delete()
        RecoveryCode.objects.filter(user=request.user).delete()
        request.session.pop("otp_verified", None)
        log_action(request, action="MFA_REMOVED", extra={"via": "api"})

        return Response({"detail": "MFA has been disabled."})


class MfaRegenerateCodesView(APIView):
    """
    POST /api/mfa/regenerate-codes/
    Body: { "code": "123456" }
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "mfa_verify"

    def post(self, request):
        from django_otp.plugins.otp_totp.models import TOTPDevice

        from accounts.models import RecoveryCode

        code = request.data.get("code", "").strip()
        device = TOTPDevice.objects.filter(user=request.user, confirmed=True).first()
        if not device:
            return Response(
                {"error": "MFA is not enabled for this account."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not device.verify_token(code):
            return Response(
                {"error": "Invalid TOTP code."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        codes = RecoveryCode.objects.generate_for(request.user)
        log_action(request, action="RECOVERY_CODES_REGENERATED", extra={"via": "api"})
        return Response({"recovery_codes": codes})


class SignoutAllView(APIView):
    """
    POST /api/security/signout-all/
    Deletes all other DB sessions for the current user + bumps mfa_trust_version.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_change"

    def post(self, request):
        from django.utils import timezone

        current_key = request.session.session_key
        user_id_str = str(request.user.pk)
        now = timezone.now()

        # Delete unexpired sessions belonging to current user except active key
        active_sessions = Session.objects.filter(expire_date__gt=now).exclude(session_key=current_key)
        sessions_to_delete = []
        for session in active_sessions.iterator():
            try:
                data = session.get_decoded()
                if data.get("_auth_user_id") == user_id_str:
                    sessions_to_delete.append(session.pk)
            except Exception:
                pass

        if sessions_to_delete:
            Session.objects.filter(pk__in=sessions_to_delete).delete()

        # Revoke all trusted-device cookies
        request.user.mfa_trust_version += 1
        request.user.save(update_fields=["mfa_trust_version"])

        log_action(request, action="SESSIONS_REVOKED", extra={"via": "api"})
        return Response({"detail": "All other sessions have been terminated."})


class MfaStatusView(APIView):
    """
    GET /api/mfa/status/ — check if MFA is set up and if this session is verified.

    This endpoint is MFA-exempt (in _EXEMPT_PREFIXES) so the middleware never
    processes the trusted-device cookie here.  We do it manually so that the
    login flow can skip the /mfa/verify step when the device is already trusted.

    Extra field:
      trusted_device — true when the signed mfa_trusted cookie is valid for this
                       user and device.  When true, otp_verified is also set in
                       the session so subsequent non-exempt requests pass the gate.
      trusted_device_hours — how many hours the trust window lasts (for display).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.conf import settings
        from django_otp.plugins.otp_totp.models import TOTPDevice

        confirmed_device = TOTPDevice.objects.filter(user=request.user, confirmed=True).first()
        confirmed = confirmed_device is not None

        # Check trusted-device cookie even though this endpoint is exempt,
        # so the login page knows whether to skip the OTP step.
        trusted = False
        if confirmed_device:
            trusted = MFAEnforcementMiddleware._cookie_is_valid(
                request, request.user, confirmed_device
            )
            if trusted and not request.session.get("otp_verified"):
                request.session["otp_verified"] = True

        return Response(
            {
                "mfa_enabled": confirmed,
                "mfa_verified_this_session": bool(request.session.get("otp_verified")),
                "mfa_enforced": getattr(settings, "MFA_ENFORCED", False),
                "role_requires_mfa": request.user.role
                in getattr(settings, "MFA_REQUIRED_ROLES", set()),
                "trusted_device": trusted,
                "trusted_device_hours": int(getattr(settings, "MFA_TRUSTED_DEVICE_HOURS", 8)),
            }
        )
