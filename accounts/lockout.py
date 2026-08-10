"""
Custom lockout response for django-axes.

Called when a user exceeds the AXES_FAILURE_LIMIT consecutive bad passwords.
Logs an ACCESS_DENIED audit entry (so the lockout appears in the audit trail)
and renders a user-friendly 403 page.
"""

import logging

from django.shortcuts import render

logger = logging.getLogger("axes")


def axes_lockout_response(request, credentials=None, *args, **kwargs):
    """
    Callable referenced by AXES_LOCKOUT_CALLABLE.

    django-axes calls this instead of raising a 403 when locking out an account.
    We use it to write an audit entry and return a styled response.
    """
    from audit.utils import log_action

    username = ""
    if credentials:
        username = credentials.get("username", "")
    elif hasattr(request, "POST"):
        username = request.POST.get("username", "")

    logger.warning(
        "Account locked after repeated failures: %s (IP: %s)",
        username,
        request.META.get("REMOTE_ADDR"),
    )

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

    return render(
        request,
        "accounts/lockout.html",
        {
            "username": username,
        },
        status=403,
    )
