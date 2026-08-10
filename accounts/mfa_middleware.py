"""
MFA Enforcement Middleware with trusted-device window.

When settings.MFA_ENFORCED is True, users whose role is in
settings.MFA_REQUIRED_ROLES must complete TOTP verification before reaching
any protected view.

Trusted-device window (MFA_TRUSTED_DEVICE_HOURS, default 8 h):
  After a successful TOTP verification the middleware writes a signed cookie
  ("mfa_trusted") binding the user ID + device ID + expiry.  On subsequent
  requests the cookie is verified with Django's signing module (tamper-proof)
  and the session-level otp_verified flag is set automatically — avoiding a
  TOTP prompt for every new browser tab on the same device.

  Re-prompt is forced on:
    - New device / browser (no cookie)
    - Expired cookie (past MFA_TRUSTED_DEVICE_HOURS)
    - Tampered / invalid cookie signature
    - Different user (cookie user_id ≠ request.user.pk)

Flow:
  authenticated, role requires MFA, MFA_ENFORCED=True
      │
      ├─ no confirmed TOTP device?  →  redirect to mfa_setup
      │
      ├─ valid trusted-device cookie? → mark otp_verified, pass through
      │
      └─ session not verified?  →  redirect to mfa_verify
           └─ after correct code  →  session['otp_verified'] = True
                                  → set trusted-device cookie

API requests (/api/*):
  Instead of a 302 redirect (which Axios follows and receives index.html),
  the middleware returns a JSON 403 with { mfa_required: true, redirect: <path> }.
  The SPA axios client intercepts this and performs a client-side redirect.
  Non-API browser requests still receive the 302 as before.

Cookie is set by mfa_verify view by calling
  MFAEnforcementMiddleware.set_trusted_device_cookie(response, user, device)

MFA-exempt paths (always allowed through):
  /accounts/login/, /accounts/logout/,
  /accounts/mfa/*, /accounts/password/change/,
  /healthz/,  /static/*, /admin/login/
"""

from django.conf import settings
from django.core import signing
from django.http import JsonResponse
from django.shortcuts import redirect

_EXEMPT_PREFIXES = (
    "/admin/login/",
    "/healthz/",
    "/static/",
    "/favicon",
    # ── SPA shell — loads before client-side auth checks run ─────────────────
    "/spa/",
    # ── API endpoints that must be reachable before MFA is complete ──────────
    "/api/csrf/",  # SPA must fetch CSRF before login
    "/api/auth/login/",  # login itself
    "/api/auth/logout/",
    "/api/mfa/",  # setup, verify, disable, regenerate-codes
    "/api/security/",  # signout-all
)

_COOKIE_NAME = "mfa_trusted"
_COOKIE_SALT = "mfa.trusted.device.v1"
_DEFAULT_HOURS = 8  # re-prompt once per shift by default


def _trusted_hours() -> int:
    return int(getattr(settings, "MFA_TRUSTED_DEVICE_HOURS", _DEFAULT_HOURS))


def _mfa_response(request, destination: str):
    """
    Return a JSON 403 for /api/* requests (SPA XHR) or a 302 for browser
    requests, directing the user to *destination* to complete MFA.
    """
    if request.path.startswith("/api/"):
        return JsonResponse(
            {"mfa_required": True, "redirect": destination},
            status=403,
        )
    return redirect(destination)


class MFAEnforcementMiddleware:
    """Enforce TOTP MFA for roles listed in MFA_REQUIRED_ROLES."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._needs_mfa_gate(request):
            from django_otp.plugins.otp_totp.models import TOTPDevice

            user = request.user

            # Check session flag first (already verified this session via TOTP, Email OTP, or recovery code)
            if request.session.get("otp_verified"):
                return self.get_response(request)

            confirmed_device = TOTPDevice.objects.filter(user=user, confirmed=True).first()

            # Check trusted-device cookie if TOTP device exists
            if confirmed_device and self._cookie_is_valid(request, user, confirmed_device):
                request.session["otp_verified"] = True
                return self.get_response(request)

            if not confirmed_device:
                return _mfa_response(request, "/spa/mfa/setup")

            # No valid session or cookie — force MFA
            return _mfa_response(request, "/spa/mfa/verify")

        return self.get_response(request)

    # ── Trusted-device cookie helpers ──────────────────────────────────────

    @staticmethod
    def _cookie_is_valid(request, user, device) -> bool:
        """Return True if a valid unexpired trusted-device cookie is present."""
        raw = request.COOKIES.get(_COOKIE_NAME)
        if not raw:
            return False
        try:
            max_age = _trusted_hours() * 3600
            payload = signing.loads(raw, salt=_COOKIE_SALT, max_age=max_age)
        except signing.BadSignature:
            return False
        except signing.SignatureExpired:
            return False
        return (
            payload.get("user_id") == user.pk
            and payload.get("device_id") == device.pk
            and payload.get("trust_version") == user.mfa_trust_version
        )

    @staticmethod
    def set_trusted_device_cookie(response, user, device):
        """
        Write a signed trusted-device cookie to *response*.

        Called by the mfa_verify view after a successful TOTP verification.
        """
        hours = _trusted_hours()
        payload = {
            "user_id": user.pk,
            "device_id": device.pk,
            "trust_version": user.mfa_trust_version,
        }
        signed = signing.dumps(payload, salt=_COOKIE_SALT)
        response.set_cookie(
            _COOKIE_NAME,
            signed,
            max_age=hours * 3600,
            httponly=True,
            secure=not settings.DEBUG,  # Secure flag off only for local dev
            samesite="Lax",
        )

    # ── Gate predicate ────────────────────────────────────────────────────

    @staticmethod
    def _needs_mfa_gate(request) -> bool:
        """Return True if this request should be checked for MFA completion."""
        if not getattr(settings, "MFA_ENFORCED", False):
            return False
        user = request.user
        if not getattr(user, "is_authenticated", False):
            return False
        required_roles = getattr(settings, "MFA_REQUIRED_ROLES", frozenset())
        if getattr(user, "role", None) not in required_roles:
            return False
        path = request.path
        return not any(path.startswith(prefix) for prefix in _EXEMPT_PREFIXES)
