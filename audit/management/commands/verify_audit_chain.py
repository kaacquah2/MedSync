"""
Management command: verify the audit log hash chain.

Usage:
    python manage.py verify_audit_chain

Walks every AuditLog row in insertion order (pk ascending) and recomputes each
row's expected hash.  Reports the first break (if any) and a summary.

Exit codes:
    0 — chain is intact
    1 — one or more breaks detected

Notes on scale:
    This linear scan is suitable for a prototype.  At production scale (millions
    of rows) you would partition by time and verify in parallel, maintaining a
    checkpoint of the last verified pk.  See ADR: audit-hash-chain.
"""

import sys

from django.core.management.base import BaseCommand, CommandError

from audit.models import AuditLog
from core.rls import rls_bypass


class Command(BaseCommand):
    help = "Verify the tamper-evident hash chain of the audit log."

    def add_arguments(self, parser):
        parser.add_argument(
            "--start-pk",
            type=int,
            default=1,
            help="Start verification from this pk (default: 1).",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print each verified row.",
        )
        parser.add_argument(
            "--rebuild",
            action="store_true",
            help="Recompute and repair row_hash and prev_hash values across all rows.",
        )
        parser.add_argument(
            "--i-understand-this-destroys-tamper-evidence",
            action="store_true",
            dest="i_understand_this_destroys_tamper_evidence",
            help="Explicitly acknowledge that rebuilding the hash chain destroys historical tamper evidence.",
        )
        parser.add_argument(
            "--anchor",
            action="store_true",
            help="After successful verification, anchor the current chain tip to external append-only storage.",
        )

    def handle(self, *args, **options):
        start_pk = options["start_pk"]
        verbose = options["verbose"]
        rebuild = options["rebuild"]

        if rebuild:
            if not options.get("i_understand_this_destroys_tamper_evidence"):
                raise CommandError(
                    "Refusing to rebuild audit chain without explicit confirmation: "
                    "--rebuild recalculates cryptographic hashes and destroys historical tamper-evidence. "
                    "To proceed, you must pass --i-understand-this-destroys-tamper-evidence."
                )

            from django.db import connection, transaction
            from django.utils import timezone

            from audit.models import AuditLogArchiveAnchor

            with rls_bypass():
                with transaction.atomic():
                    with connection.cursor() as cursor:
                        if connection.vendor == "postgresql":
                            cursor.execute(
                                "ALTER TABLE audit_auditlog DISABLE TRIGGER trg_audit_log_immutable"
                            )
                        elif connection.vendor == "sqlite":
                            cursor.execute("DROP TRIGGER IF EXISTS trg_audit_log_immutable_update")

                        # If there is a pre-existing anchor preceding the first row, start from it
                        first_row = AuditLog.objects.order_by("pk").first()
                        prev_hash = ""
                        if first_row:
                            latest_anchor = (
                                AuditLogArchiveAnchor.objects.filter(last_row_pk__lt=first_row.pk)
                                .order_by("-last_row_pk")
                                .first()
                            )
                            if latest_anchor:
                                prev_hash = latest_anchor.last_row_hash

                        count = 0
                        for entry in AuditLog.objects.order_by("pk").iterator():
                            fields = AuditLog._chain_fields_for(entry)
                            new_hash = AuditLog.compute_row_hash(prev_hash, fields)
                            AuditLog.objects.filter(pk=entry.pk).update(
                                prev_hash=prev_hash, row_hash=new_hash
                            )
                            prev_hash = new_hash
                            count += 1

                        # Write its own audit entry documenting the rebuild
                        now = timezone.now()
                        rebuild_entry = AuditLog(
                            actor=None,
                            actor_username="system:cli",
                            actor_role="admin",
                            actor_hospital="",
                            action=getattr(
                                AuditLog.Action, "REBUILD_AUDIT_CHAIN", "VALIDATE_AUDIT_CHAIN"
                            ),
                            timestamp=now,
                            target_type="AuditLog",
                            target_id="all",
                            patient_nhid="",
                            is_cross_hospital=False,
                            ip_address="127.0.0.1",
                            user_agent="manage.py verify_audit_chain --rebuild",
                            extra={
                                "rebuilt_rows": count,
                                "flag": "--i-understand-this-destroys-tamper-evidence",
                                "warning": "Chain was administratively re-sealed; historical tamper-evidence before this point was reset.",
                            },
                        )
                        rebuild_fields = AuditLog._chain_fields_for(rebuild_entry)
                        rebuild_entry.prev_hash = prev_hash
                        rebuild_entry.row_hash = AuditLog.compute_row_hash(
                            prev_hash, rebuild_fields
                        )
                        rebuild_entry.save()

                        if connection.vendor == "postgresql":
                            cursor.execute(
                                "ALTER TABLE audit_auditlog ENABLE TRIGGER trg_audit_log_immutable"
                            )
                        elif connection.vendor == "sqlite":
                            cursor.execute(
                                "CREATE TRIGGER IF NOT EXISTS trg_audit_log_immutable_update "
                                "BEFORE UPDATE ON audit_auditlog BEGIN "
                                "SELECT RAISE(ABORT, 'audit_auditlog is immutable: UPDATE prohibited'); END;"
                            )

            self.stdout.write(
                self.style.SUCCESS(
                    f"Rebuilt audit hash chain across {count} row(s) and logged rebuild audit entry #{rebuild_entry.pk}."
                )
            )
            return

        queryset = (
            AuditLog.objects.filter(pk__gte=start_pk)
            .only(
                "pk",
                "prev_hash",
                "row_hash",
                "actor_username",
                "actor_role",
                "actor_hospital",
                "action",
                "timestamp",
                "target_type",
                "target_id",
                "patient_nhid",
                "is_cross_hospital",
                "ip_address",
                "extra",
            )
            .order_by("pk")
        )

        import hashlib
        import os

        from django.conf import settings

        from audit.anchors import create_live_anchor, read_anchor_ledger
        from audit.models import AuditLogArchiveAnchor

        self.stdout.write("Verifying WORM archive file system anchors and append-only ledger...")
        archive_breaks = 0

        with rls_bypass():
            anchors = list(AuditLogArchiveAnchor.objects.order_by("last_row_pk"))

        # 1. Verify append-only external ledger against database anchors
        ledger_entries = read_anchor_ledger()
        if ledger_entries:
            db_anchor_map = {a.last_row_pk: a for a in anchors}
            for le in ledger_entries:
                l_pk = le.get("last_row_pk")
                if l_pk not in db_anchor_map:
                    self.stderr.write(
                        self.style.ERROR(
                            f"LEDGER INTEGRITY BREACH: External ledger contains anchor for PK={l_pk} "
                            f"('{le.get('archive_filename')}'), but it was deleted from the database!"
                        )
                    )
                    archive_breaks += 1
                else:
                    db_a = db_anchor_map[l_pk]
                    if db_a.last_row_hash != le.get(
                        "last_row_hash"
                    ) or db_a.archive_file_hash != le.get("archive_file_hash"):
                        self.stderr.write(
                            self.style.ERROR(
                                f"LEDGER CORRUPTION: External ledger anchor for PK={l_pk} "
                                f"does not match database record!"
                            )
                        )
                        archive_breaks += 1

        # 2. Verify archive/checkpoint files on disk
        for anchor in anchors:
            archive_dir = os.path.join(settings.MEDIA_ROOT, "audit_archives")
            file_path = os.path.join(archive_dir, anchor.archive_filename)

            if not os.path.exists(file_path):
                self.stderr.write(
                    self.style.ERROR(
                        f"ARCHIVE ERROR: File '{anchor.archive_filename}' not found for anchor PK={anchor.last_row_pk}."
                    )
                )
                archive_breaks += 1
                continue

            with open(file_path, encoding="utf-8") as f:
                content = f.read()

            computed_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            if computed_hash != anchor.archive_file_hash:
                self.stderr.write(
                    self.style.ERROR(
                        f"ARCHIVE CORRUPTION: File '{anchor.archive_filename}' hash mismatch!\n"
                        f"  stored  : {anchor.archive_file_hash}\n"
                        f"  computed: {computed_hash}"
                    )
                )
                archive_breaks += 1
            else:
                if verbose:
                    self.stdout.write(f"  OK archive '{anchor.archive_filename}' verified.")

        total = 0
        breaks = archive_breaks
        prev_row_hash = None
        anchor_row_map = {a.last_row_pk: a for a in anchors}

        # audit_auditlog has FORCE ROW LEVEL SECURITY; management commands run
        # without a request context so we need the explicit bypass.
        with rls_bypass():
            first_db_row = queryset.first()
            if first_db_row:
                latest_anchor = (
                    AuditLogArchiveAnchor.objects.filter(last_row_pk__lt=first_db_row.pk)
                    .order_by("-last_row_pk")
                    .first()
                )
                if latest_anchor:
                    prev_row_hash = latest_anchor.last_row_hash
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Anchoring database validation to WORM archive PK={latest_anchor.last_row_pk} hash={prev_row_hash[:12]}…"
                        )
                    )

            for entry in queryset.iterator(chunk_size=1000):
                total += 1
                if prev_row_hash is None:
                    # Anchor verification to the first evaluated row's stored prev_hash
                    # (allows verification post-pruning or when using --start-pk)
                    prev_row_hash = entry.prev_hash

                expected_hash = AuditLog.compute_row_hash(
                    prev_row_hash,
                    AuditLog._chain_fields_for(entry),
                )

                hash_matches = entry.row_hash == expected_hash
                prev_matches = entry.prev_hash == prev_row_hash

                if not (hash_matches and prev_matches):
                    breaks += 1
                    self.stderr.write(
                        self.style.ERROR(
                            f"CHAIN BREAK at pk={entry.pk} "
                            f"({entry.actor_username} / {entry.action} / {entry.timestamp})\n"
                            f"  stored  : {entry.row_hash}\n"
                            f"  expected: {expected_hash}\n"
                            f"  prev_hash match: {prev_matches}"
                        )
                    )
                else:
                    if verbose:
                        self.stdout.write(f"  OK pk={entry.pk} hash={entry.row_hash[:12]}…")

                # Check if this row was anchored externally and verify anchor continuity
                if entry.pk in anchor_row_map:
                    anch = anchor_row_map[entry.pk]
                    if entry.row_hash != anch.last_row_hash:
                        breaks += 1
                        self.stderr.write(
                            self.style.ERROR(
                                f"ANCHOR BREAK at pk={entry.pk}: "
                                f"row_hash ({entry.row_hash}) does not match published external anchor ({anch.last_row_hash})!\n"
                                f"External anchor mismatch indicates tampering despite valid internal chain."
                            )
                        )

                # For the next iteration, use what was STORED (not recomputed) so we
                # only report the first break and correctly flag all subsequent rows too.
                prev_row_hash = entry.row_hash or expected_hash

        if total == 0:
            self.stdout.write(self.style.WARNING("No audit rows found."))
            return

        if breaks == 0:
            self.stdout.write(
                self.style.SUCCESS(f"Audit chain intact — {total} row(s) verified, 0 breaks.")
            )
            if options.get("anchor"):
                new_anchor = create_live_anchor()
                if new_anchor:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Published new external anchor for PK={new_anchor.last_row_pk} "
                            f"hash={new_anchor.last_row_hash[:12]}… to '{new_anchor.archive_filename}'."
                        )
                    )
                else:
                    self.stdout.write("Audit chain tip was already anchored.")
        else:
            self.stderr.write(
                self.style.ERROR(
                    f"{breaks} break(s) detected in {total} row(s). Investigate immediately."
                )
            )
            sys.exit(1)
