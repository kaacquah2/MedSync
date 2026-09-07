"""
Append-only external anchor publishing and verification utilities.
"""

import hashlib
import json
import logging
import os

from django.conf import settings
from django.utils import timezone

from audit.models import AuditLog, AuditLogArchiveAnchor
from core.rls import rls_bypass

logger = logging.getLogger(__name__)


def get_anchor_ledger_path() -> str:
    """Return the absolute path to the append-only anchor ledger file."""
    ledger_path = getattr(settings, "AUDIT_ANCHOR_LEDGER_PATH", None)
    if ledger_path:
        return ledger_path
    archive_dir = os.path.join(settings.MEDIA_ROOT, "audit_archives")
    os.makedirs(archive_dir, exist_ok=True)
    return os.path.join(archive_dir, "anchor_ledger.jsonl")


def append_anchor_to_ledger(anchor: AuditLogArchiveAnchor) -> str:
    """
    Append an anchor record to the external append-only ledger.
    Flushes and fsyncs the file to guarantee durability.
    """
    ledger_path = get_anchor_ledger_path()
    os.makedirs(os.path.dirname(ledger_path), exist_ok=True)

    record = {
        "archive_filename": anchor.archive_filename,
        "last_row_pk": anchor.last_row_pk,
        "last_row_hash": anchor.last_row_hash,
        "archive_file_hash": anchor.archive_file_hash,
        "created_at": anchor.created_at.isoformat()
        if anchor.created_at
        else timezone.now().isoformat(),
    }
    line = json.dumps(record, sort_keys=True) + "\n"

    with open(ledger_path, "a", encoding="utf-8") as f:
        f.write(line)
        f.flush()
        os.fsync(f.fileno())

    return ledger_path


def read_anchor_ledger() -> list[dict]:
    """Read all entries from the append-only anchor ledger."""
    ledger_path = get_anchor_ledger_path()
    if not os.path.exists(ledger_path):
        return []

    entries = []
    with open(ledger_path, encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError as exc:
                logger.error("Failed to parse ledger line %d: %s", line_num, exc)
    return entries


def create_live_anchor() -> AuditLogArchiveAnchor | None:
    """
    Create a periodic checkpoint anchor for the latest row in the live audit log,
    write the anchor checkpoint file to WORM storage, and record in the append-only ledger.
    """
    with rls_bypass():
        last_entry = AuditLog.objects.order_by("-pk").first()
        if not last_entry:
            return None

        # Check if already anchored at or beyond this PK
        latest_existing = AuditLogArchiveAnchor.objects.filter(
            last_row_pk__gte=last_entry.pk
        ).first()
        if latest_existing:
            return None

        archive_dir = os.path.join(settings.MEDIA_ROOT, "audit_archives")
        os.makedirs(archive_dir, exist_ok=True)

        ts_str = (
            last_entry.timestamp.strftime("%Y%m%d_%H%M%S") if last_entry.timestamp else "latest"
        )
        filename = f"audit_anchor_{ts_str}_pk_{last_entry.pk}.json"
        file_path = os.path.join(archive_dir, filename)

        checkpoint_data = {
            "anchor_type": "CHECKPOINT",
            "last_row_pk": last_entry.pk,
            "last_row_hash": last_entry.row_hash,
            "timestamp": last_entry.timestamp.isoformat() if last_entry.timestamp else "",
            "action": last_entry.action,
            "actor_username": last_entry.actor_username,
            "created_at": timezone.now().isoformat(),
        }

        content = json.dumps(checkpoint_data, indent=2, sort_keys=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        file_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        anchor = AuditLogArchiveAnchor.objects.create(
            archive_filename=filename,
            last_row_pk=last_entry.pk,
            last_row_hash=last_entry.row_hash,
            archive_file_hash=file_hash,
        )
        append_anchor_to_ledger(anchor)
        return anchor
