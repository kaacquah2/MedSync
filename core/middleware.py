"""
Core middleware for the mEd EMR.

RLSContextMiddleware
--------------------
Sets PostgreSQL session GUCs (custom parameters) used by Row-Level Security
policies on audit_auditlog and records_encounter.  Must run AFTER
AuthenticationMiddleware so request.user is populated.

Three GUCs are set at the session level (is_local=false) so they persist
across the implicit per-statement auto-commit transactions Django uses under
autocommit mode.  Session-level GUCs are safe here because:
  - Django uses persistent connections (CONN_MAX_AGE); we reset in a finally
    block so the connection returns to a safe default state after each request.
  - We deliberately do NOT use transaction.atomic() to wrap the request, because
    that would turn log_action's own transaction.atomic() into a savepoint,
    causing audit entries to roll back if the view later raises an exception.

GUCs set per request:
  app.user_id       — authenticated user PK ('' when anonymous)
  app.hospital_id   — user's home hospital PK ('' for super_admin / no hospital)
  app.is_admin      — 'on' when user.is_admin_level, else 'off'

The policies also check app.bypass_rls (set by core.rls.rls_bypass() in
management commands).  The middleware resets this to 'off' in the finally block
as a precaution.

No-op on SQLite (tests / local dev without Neon).

NoCachePHIMiddleware
--------------------
Sets Cache-Control: no-store on every authenticated, non-static response.

Without this, browsers cache PHI pages.  On a shared clinical workstation
the back button can display a previous patient's record after the user logs
out or switches patients — a patient-safety and confidentiality risk.

Static files (WhiteNoise) and unauthenticated pages are left unaffected.
Django's built-in auth views (login, logout, password-change) already emit
no-cache headers via @never_cache internally; this middleware covers the
application's own clinical views.
"""

import logging
from contextlib import suppress

from django.contrib.sessions.exceptions import SessionInterrupted
from django.contrib.sessions.middleware import SessionMiddleware
from django.db import connection
from django.http import HttpResponse, JsonResponse

logger = logging.getLogger(__name__)


class SessionInterruptedMiddleware(SessionMiddleware):
    """
    Subclasses Django's SessionMiddleware to handle SessionInterrupted exceptions gracefully.

    This exception is raised if a concurrent request (e.g., a logout request)
    deleted the session from the database before the current request completes,
    making the session save at the end of the request fail.
    """

    def __call__(self, request):
        try:
            return super().__call__(request)
        except SessionInterrupted:
            logger.info(
                "Session interrupted for request path: %s (likely concurrent logout)", request.path
            )
            if request.path.startswith("/api/"):
                return JsonResponse(
                    {"error": "Session interrupted. The session was deleted concurrently."},
                    status=400,
                )
            return HttpResponse(
                "Session interrupted. The session was deleted concurrently.",
                status=400,
                content_type="text/plain",
            )


class RLSContextMiddleware:
    """
    Set per-request PostgreSQL GUCs for Row-Level Security policies.

    Must be placed AFTER AuthenticationMiddleware in the MIDDLEWARE list.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if connection.vendor != "postgresql":
            # SQLite (tests / local dev) — skip; no RLS policies exist there.
            return self.get_response(request)

        user = getattr(request, "user", None)
        uid = str(user.pk) if getattr(user, "is_authenticated", False) else ""
        hid = str(user.hospital_id) if uid and getattr(user, "hospital_id", None) else ""
        adm = "on" if uid and getattr(user, "is_admin_level", False) else "off"

        with connection.cursor() as cur:
            cur.execute(
                "SELECT set_config('app.user_id',     %s, false),"
                "       set_config('app.hospital_id', %s, false),"
                "       set_config('app.is_admin',    %s, false)",
                [uid, hid, adm],
            )

        try:
            return self.get_response(request)
        finally:
            # Reset to safe defaults so a pooled connection is never reused
            # with a stale user identity.
            with suppress(Exception):
                with connection.cursor() as cur:
                    cur.execute(
                        "SELECT set_config('app.user_id',     '', false),"
                        "       set_config('app.hospital_id', '', false),"
                        "       set_config('app.is_admin',    'off', false),"
                        "       set_config('app.bypass_rls',  'off', false)"
                    )


_STATIC_PREFIXES = ("/static/", "/favicon")


class NoCachePHIMiddleware:
    """Add Cache-Control: no-store to authenticated responses."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Only apply to authenticated users (PHI responses)
        if not getattr(request.user, "is_authenticated", False):
            return response

        # Leave static assets alone (WhiteNoise manages their cache headers)
        path = request.path
        if any(path.startswith(p) for p in _STATIC_PREFIXES):
            return response

        # Set no-store so the browser neither caches nor serves from cache (evicting from bfcache)
        response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response["Pragma"] = "no-cache"
        return response


class ContentSecurityPolicyMiddleware:
    """
    Sets Content-Security-Policy (CSP) and security headers on responses.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if "Content-Security-Policy" not in response:
            csp = (
                "default-src 'self'; "
                "script-src 'self'; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                "font-src 'self' https://fonts.gstatic.com data:; "
                "img-src 'self' data: blob:; "
                "connect-src 'self'; "
                "frame-ancestors 'none'; "
                "object-src 'none'; "
                "base-uri 'self';"
            )
            response["Content-Security-Policy"] = csp

        if "X-Content-Type-Options" not in response:
            response["X-Content-Type-Options"] = "nosniff"
        if "X-Frame-Options" not in response:
            response["X-Frame-Options"] = "DENY"
        if "Referrer-Policy" not in response:
            response["Referrer-Policy"] = "strict-origin-when-cross-origin"

        return response
