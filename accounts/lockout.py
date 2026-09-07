"""
Custom lockout response for django-axes.

Called when a user exceeds the AXES_FAILURE_LIMIT consecutive bad passwords.
Logs an ACCESS_DENIED audit entry (so the lockout appears in the audit trail)
and renders a user-friendly 403 page.
"""

import json
import logging

from django.http import HttpResponse, JsonResponse
from django.shortcuts import render

logger = logging.getLogger("axes")


def _wants_json(request):
    if not request:
        return True
    return (
        request.path.startswith("/api/")
        or request.path.startswith("/fhir/")
        or "application/json" in request.headers.get("Accept", "")
        or getattr(request, "content_type", "") == "application/json"
    )


def axes_lockout_response(request, original_response=None, credentials=None, *args, **kwargs):
    """
    Callable referenced by AXES_LOCKOUT_CALLABLE.

    django-axes calls this instead of raising a 403 when locking out an account.
    We use it to write an audit entry and return a styled response (JSON for API/SPA,
    or HTML for browser navigation).
    """
    from audit.utils import log_action

    # django-axes may invoke with (request, credentials) or (request, original_response, credentials)
    if credentials is None and isinstance(original_response, dict):
        credentials = original_response

    username = ""
    if isinstance(credentials, dict):
        username = credentials.get("username", "")
    elif hasattr(request, "POST") and request.POST.get("username"):
        username = request.POST.get("username", "")
    elif hasattr(request, "body"):
        try:
            body_data = json.loads(request.body)
            if isinstance(body_data, dict):
                username = body_data.get("username", "")
        except Exception:
            pass

    logger.warning(
        "Account locked after repeated failures: %s (IP: %s)",
        username,
        request.META.get("REMOTE_ADDR") if request else "unknown",
    )

    if request:
        try:
            log_action(
                request,
                action="ACCESS_DENIED",
                extra={
                    "reason": "brute_force_lockout",
                    "username_attempted": username,
                },
            )
        except Exception:
            pass  # audit failure must never block the lockout response

    if _wants_json(request):
        return JsonResponse(
            {
                "error": "Account locked due to too many failed login attempts. Please try again later.",
                "detail": "Too many failed login attempts. Account locked.",
            },
            status=403,
        )

    try:
        return render(
            request,
            "accounts/lockout.html",
            {
                "username": username,
            },
            status=403,
        )
    except Exception:
        return HttpResponse(
            "<!DOCTYPE html><html><head><title>403 Forbidden - Account Locked</title></head>"
            "<body><h1>Account Locked</h1>"
            "<p>Too many failed login attempts. Please try again later or contact your administrator.</p>"
            "</body></html>",
            status=403,
            content_type="text/html",
        )
