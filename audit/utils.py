"""
Convenience helper for writing audit log entries from views.

Usage:
    from audit.utils import log_action

    log_action(
        request,
        action="VIEW_PATIENT",
        target=patient_obj,
        patient=patient_obj,
        is_cross_hospital=True,
    )
"""

import logging
import time

from django.db import connection, transaction
from django.utils import timezone

from core.rls import rls_bypass

logger = logging.getLogger(__name__)


def _get_ip(request) -> str | None:
    """Extract the real client IP from the request.

    Reads TRUSTED_PROXY_COUNT (default 1) from settings to determine how many
    reverse-proxy hops (nginx, load-balancer) precede this application.
    The real client IP is XFF[-TRUSTED_PROXY_COUNT]; IPs to the left are
    client-supplied and must not be trusted for audit purposes.
    """
    if not request or not hasattr(request, "META"):
        return None

    from django.conf import settings

    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        trusted = int(getattr(settings, "TRUSTED_PROXY_COUNT", 1))
        ips = [ip.strip() for ip in xff.split(",") if ip.strip()]
        if ips:
            idx = max(len(ips) - trusted, 0)
            return ips[idx]
    return request.META.get("REMOTE_ADDR")


# Arbitrary constant used as a Postgres advisory-lock ID to serialize hash-chain
# writes across multiple workers.  Must be the same value on all app processes.
# See docs/adr/005-audit-hash-chain.md for the concurrency rationale.
_CHAIN_LOCK_ID = 0x6D456400  # "mEd\x00" in ASCII → 1835102208


def log_action(
    request,
    action: str,
    target=None,
    patient=None,
    is_cross_hospital: bool = False,
    extra: dict | None = None,
):
    """
    Write one immutable AuditLog entry.

    Parameters
    ----------
    request           : the current Django request
    action            : AuditLog.Action string (e.g. "VIEW_PATIENT")
    target            : the Django model instance being accessed/modified
    patient           : the Patient instance (for patient_nhid)
    is_cross_hospital : True when clinician's hospital ≠ record's origin hospital
    extra             : arbitrary JSON-serialisable dict for additional context
    """
    from .models import AuditLog

    user = request.user if (request and hasattr(request, "user")) else None
    authenticated = user is not None and user.is_authenticated

    now = timezone.now()
    entry = AuditLog(
        actor=user if authenticated else None,
        actor_username=user.username if authenticated else "",
        actor_role=getattr(user, "role", "") if authenticated else "",
        actor_hospital=str(user.hospital)
        if (authenticated and getattr(user, "hospital", None))
        else "",
        action=action,
        timestamp=now,
        target_type=target.__class__.__name__ if target else "",
        target_id=str(target.pk) if target else "",
        patient_nhid=patient.universal_id if patient else "",
        is_cross_hospital=is_cross_hospital,
        ip_address=_get_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:500]
        if (request and hasattr(request, "META"))
        else "",
        extra=extra or {},
    )

    # ── Hash chain write (synchronous & durable) ──────────────────────────
    t0 = time.monotonic()
    with rls_bypass(), transaction.atomic():
        if connection.vendor == "postgresql":
            with connection.cursor() as cur:
                cur.execute("SELECT pg_advisory_xact_lock(%s)", [_CHAIN_LOCK_ID])
        lock_wait = time.monotonic() - t0
        if lock_wait > 0.05:
            logger.warning(
                "Audit log advisory lock acquisition took %.3fs (exceeded 50ms threshold)",
                lock_wait,
            )

        last = AuditLog.objects.order_by("-pk").only("row_hash").first()
        prev_hash = last.row_hash if (last and last.row_hash) else ""

        fields = AuditLog._chain_fields_for(entry)
        entry.prev_hash = prev_hash
        entry.row_hash = AuditLog.compute_row_hash(prev_hash, fields)

        entry.save()

    return entry
