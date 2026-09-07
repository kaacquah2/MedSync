"""
Custom HTTP error handlers.

Registered in emr/urls.py as handler403, handler404, handler500.
The 403 handler writes an ACCESS_DENIED audit entry so that permission
violations appear in the security audit trail.
"""

import logging

from django.http import JsonResponse
from django.shortcuts import render

logger = logging.getLogger("django.security")


def _wants_json(request):
    return (
        request.path.startswith("/api/")
        or request.path.startswith("/fhir/")
        or "application/json" in request.headers.get("Accept", "")
    )


def handler_403(request, exception=None):
    """403 Forbidden — logs to audit trail and renders styled page or returns JSON."""
    logger.warning(
        "Access denied: %s %s (user=%s)",
        request.method,
        request.path,
        request.user.username if request.user.is_authenticated else "<anon>",
    )

    try:
        from audit.utils import log_action

        log_action(
            request,
            action="ACCESS_DENIED",
            extra={"path": request.path, "method": request.method},
        )
    except Exception:
        pass  # audit failure must never break the error response

    if _wants_json(request):
        return JsonResponse({"error": "Access denied.", "status_code": 403}, status=403)

    return render(request, "403.html", status=403)


def handler_404(request, exception=None):
    if _wants_json(request):
        return JsonResponse({"error": "Resource not found.", "status_code": 404}, status=404)
    return render(request, "404.html", status=404)


def handler_500(request):
    if _wants_json(request):
        return JsonResponse(
            {"error": "An unexpected server error occurred.", "status_code": 500},
            status=500,
        )
    return render(request, "500.html", status=500)
