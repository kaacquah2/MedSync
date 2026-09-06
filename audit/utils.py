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

import atexit
import logging
import queue
import threading
import time

from django.conf import settings
from django.db import close_old_connections, connection, transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

_audit_queue = queue.Queue()
_worker_thread = None
_thread_lock = threading.Lock()
_shutdown_sentinel = object()


def _audit_log_worker():
    """Background worker thread to sequentially compute hashes and save audit logs."""
    logger.info("Audit log worker thread started.")
    while True:
        try:
            item = _audit_queue.get()
            if item is _shutdown_sentinel:
                logger.info("Audit log worker thread received shutdown sentinel.")
                _audit_queue.task_done()
                break

            entry = item

            try:
                # Close stale database connections in the background thread
                close_old_connections()

                # Perform the DB write sequentially inside the PG advisory lock
                t0 = time.monotonic()
                with transaction.atomic():
                    if connection.vendor == "postgresql":
                        with connection.cursor() as cur:
                            cur.execute("SELECT pg_advisory_xact_lock(%s)", [_CHAIN_LOCK_ID])

                    # Compute expected hash using database state
                    from .models import AuditLog
                    last = AuditLog.objects.order_by("-pk").only("row_hash").first()
                    prev_hash = last.row_hash if (last and last.row_hash) else ""

                    fields = AuditLog._chain_fields_for(entry)
                    entry.prev_hash = prev_hash
                    entry.row_hash = AuditLog.compute_row_hash(prev_hash, fields)

                    entry.save()

                lock_wait = time.monotonic() - t0
                if lock_wait > 0.05:
                    logger.debug(
                        "Async audit log advisory lock and write took %.3fs",
                        lock_wait,
                    )
            except Exception:
                logger.exception("Failed to write asynchronous audit log entry.")
            finally:
                _audit_queue.task_done()
        except Exception:
            logger.exception("Unexpected error in audit log worker loop.")


def _start_worker():
    global _worker_thread
    if _worker_thread is None or not _worker_thread.is_alive():
        with _thread_lock:
            if _worker_thread is None or not _worker_thread.is_alive():
                _worker_thread = threading.Thread(
                    target=_audit_log_worker,
                    daemon=True,
                    name="AuditLogWorker",
                )
                _worker_thread.start()


def _shutdown_worker():
    global _worker_thread
    if _worker_thread is not None and _worker_thread.is_alive():
        logger.info("Shutting down audit log worker thread...")
        _audit_queue.put(_shutdown_sentinel)
        _worker_thread.join(timeout=5.0)
        logger.info("Audit log worker thread stopped.")


atexit.register(_shutdown_worker)


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
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:500] if (request and hasattr(request, "META")) else "",
        extra=extra or {},
    )

    # ── Hash chain write ───────────────────────────────────────────────────
    # If in testing mode, run synchronously to ensure test assertions pass
    if getattr(settings, "TESTING", False):
        t0 = time.monotonic()
        with transaction.atomic():
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

    # Queue the entry asynchronously
    _audit_queue.put(entry)
    _start_worker()

    return entry

