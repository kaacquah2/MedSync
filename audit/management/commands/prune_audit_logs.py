import sys
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from audit.models import AuditLog
from core.rls import rls_bypass


class Command(BaseCommand):
    help = (
        "Archive and prune audit log entries older than a specified number of days (default: 30) "
        "using the Archive-then-Anchor WORM pattern to preserve hash-chain continuity."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Archive and prune entries older than this many days (default: 30).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force pruning without confirmation.",
        )

    def handle(self, *args, **options):
        days = options["days"]
        force = options["force"]

        if days < 1:
            self.stderr.write(self.style.ERROR("Error: --days must be at least 1."))
            sys.exit(1)

        cutoff = timezone.now() - timedelta(days=days)

        with rls_bypass():
            count = AuditLog.objects.filter(timestamp__lt=cutoff).count()

        if count == 0:
            self.stdout.write(self.style.SUCCESS(f"No audit logs found older than {days} days."))
            return

        if not force:
            self.stdout.write(
                self.style.WARNING(
                    f"You are about to archive and prune {count} audit log entries older than {days} days (cutoff: {cutoff}).\n"
                    "NOTE: To preserve SHA-256 hash-chain continuity, entries will be serialized into a signed WORM JSON "
                    "archive in media/audit_archives/, registered in AuditLogArchiveAnchor, and committed to anchor_ledger.jsonl "
                    "before database rows are pruned."
                )
            )
            confirm = input("Are you sure you want to proceed? [y/N]: ").strip().lower()
            if confirm != "y":
                self.stdout.write("Pruning cancelled.")
                return

        import hashlib
        import json
        import os

        from django.conf import settings
        from django.db import connection

        from audit.models import AuditLogArchiveAnchor

        with rls_bypass():
            # Fetch entries to delete in order of PK
            targets = list(AuditLog.objects.filter(timestamp__lt=cutoff).order_by("pk"))

            if not targets:
                self.stdout.write("No logs matched the cutoff criteria at pruning time.")
                return

            last_target = targets[-1]
            last_pk = last_target.pk
            last_hash = last_target.row_hash

            # Serialize to file in media root
            archive_dir = os.path.join(settings.MEDIA_ROOT, "audit_archives")
            os.makedirs(archive_dir, exist_ok=True)

            start_ts = targets[0].timestamp.strftime("%Y%m%d_%H%M%S")
            end_ts = last_target.timestamp.strftime("%Y%m%d_%H%M%S")
            filename = f"audit_archive_{start_ts}_to_{end_ts}_pk_{targets[0].pk}_to_{last_pk}.json"
            file_path = os.path.join(archive_dir, filename)

            data_list = []
            for entry in targets:
                data_list.append(
                    {
                        "pk": entry.pk,
                        "actor_username": entry.actor_username,
                        "actor_role": entry.actor_role,
                        "actor_hospital": entry.actor_hospital,
                        "action": entry.action,
                        "timestamp": entry.timestamp.isoformat() if entry.timestamp else "",
                        "target_type": entry.target_type,
                        "target_id": entry.target_id,
                        "patient_nhid": entry.patient_nhid,
                        "is_cross_hospital": entry.is_cross_hospital,
                        "ip_address": entry.ip_address,
                        "user_agent": entry.user_agent,
                        "extra": entry.extra,
                        "prev_hash": entry.prev_hash,
                        "row_hash": entry.row_hash,
                    }
                )

            json_content = json.dumps(data_list, indent=2, sort_keys=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(json_content)

            file_hash = hashlib.sha256(json_content.encode("utf-8")).hexdigest()

            with transaction.atomic():
                # Save the validation anchor
                anchor = AuditLogArchiveAnchor.objects.create(
                    archive_filename=filename,
                    last_row_pk=last_pk,
                    last_row_hash=last_hash,
                    archive_file_hash=file_hash,
                )
                from audit.anchors import append_anchor_to_ledger

                append_anchor_to_ledger(anchor)

                # Delete the database entries
                with connection.cursor() as cursor:
                    if connection.vendor == "postgresql":
                        cursor.execute(
                            "ALTER TABLE audit_auditlog DISABLE TRIGGER trg_audit_log_immutable"
                        )
                    elif connection.vendor == "sqlite":
                        cursor.execute("DROP TRIGGER IF EXISTS trg_audit_log_immutable_delete")

                    cursor.execute("DELETE FROM audit_auditlog WHERE timestamp < %s", [cutoff])
                    deleted = cursor.rowcount

                    if connection.vendor == "postgresql":
                        cursor.execute(
                            "ALTER TABLE audit_auditlog ENABLE TRIGGER trg_audit_log_immutable"
                        )
                    elif connection.vendor == "sqlite":
                        cursor.execute(
                            "CREATE TRIGGER IF NOT EXISTS trg_audit_log_immutable_delete "
                            "BEFORE DELETE ON audit_auditlog BEGIN "
                            "SELECT RAISE(ABORT, 'audit_auditlog is immutable: DELETE prohibited'); END;"
                        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully archived and pruned {deleted} audit log entries.\n"
                f"WORM archive saved: media/audit_archives/{filename}\n"
                "Chain Continuity Preserved: Verification will anchor to this archive's final row hash."
            )
        )
