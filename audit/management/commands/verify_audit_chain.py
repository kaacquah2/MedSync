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

from django.core.management.base import BaseCommand

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

    def handle(self, *args, **options):
        start_pk = options["start_pk"]
        verbose = options["verbose"]
        rebuild = options["rebuild"]

        if rebuild:
            from django.db import connection, transaction

            with rls_bypass():
                with transaction.atomic():
                    with connection.cursor() as cursor:
                        if connection.vendor == "postgresql":
                            cursor.execute("ALTER TABLE audit_auditlog DISABLE TRIGGER trg_audit_log_immutable")
                        elif connection.vendor == "sqlite":
                            cursor.execute("DROP TRIGGER IF EXISTS trg_audit_log_immutable_update")

                        prev_hash = ""
                        count = 0
                        for entry in AuditLog.objects.order_by("pk").iterator():
                            fields = AuditLog._chain_fields_for(entry)
                            new_hash = AuditLog.compute_row_hash(prev_hash, fields)
                            AuditLog.objects.filter(pk=entry.pk).update(prev_hash=prev_hash, row_hash=new_hash)
                            prev_hash = new_hash
                            count += 1

                        if connection.vendor == "postgresql":
                            cursor.execute("ALTER TABLE audit_auditlog ENABLE TRIGGER trg_audit_log_immutable")
                        elif connection.vendor == "sqlite":
                            cursor.execute(
                                "CREATE TRIGGER IF NOT EXISTS trg_audit_log_immutable_update "
                                "BEFORE UPDATE ON audit_auditlog BEGIN "
                                "SELECT RAISE(ABORT, 'audit_auditlog is immutable: UPDATE prohibited'); END;"
                            )

            self.stdout.write(self.style.SUCCESS(f"Rebuilt audit hash chain across {count} row(s)."))
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

        total = 0
        breaks = 0
        prev_row_hash = None

        # audit_auditlog has FORCE ROW LEVEL SECURITY; management commands run
        # without a request context so we need the explicit bypass.
        with rls_bypass():
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
        else:
            self.stderr.write(
                self.style.ERROR(
                    f"{breaks} break(s) detected in {total} row(s). Investigate immediately."
                )
            )
            sys.exit(1)
