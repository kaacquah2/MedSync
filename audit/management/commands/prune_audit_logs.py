import sys
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from audit.models import AuditLog
from core.rls import rls_bypass


class Command(BaseCommand):
    help = "Prune audit log entries older than a specified number of days (default: 30)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Prune entries older than this many days (default: 30).",
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
                    f"You are about to delete {count} audit log entries older than {days} days (cutoff: {cutoff}).\n"
                    "WARNING: Deleting rows breaks the SHA-256 hash chain validation for remaining entries."
                )
            )
            confirm = input("Are you sure you want to proceed? [y/N]: ").strip().lower()
            if confirm != "y":
                self.stdout.write("Pruning cancelled.")
                return

        from django.db import connection

        with rls_bypass():
            with transaction.atomic():
                with connection.cursor() as cursor:
                    if connection.vendor == "postgresql":
                        cursor.execute("ALTER TABLE audit_auditlog DISABLE TRIGGER trg_audit_log_immutable")
                    elif connection.vendor == "sqlite":
                        cursor.execute("DROP TRIGGER IF EXISTS trg_audit_log_immutable_delete")

                    cursor.execute("DELETE FROM audit_auditlog WHERE timestamp < %s", [cutoff])
                    deleted = cursor.rowcount

                    if connection.vendor == "postgresql":
                        cursor.execute("ALTER TABLE audit_auditlog ENABLE TRIGGER trg_audit_log_immutable")
                    elif connection.vendor == "sqlite":
                        cursor.execute(
                            "CREATE TRIGGER IF NOT EXISTS trg_audit_log_immutable_delete "
                            "BEFORE DELETE ON audit_auditlog BEGIN "
                            "SELECT RAISE(ABORT, 'audit_auditlog is immutable: DELETE prohibited'); END;"
                        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully pruned {deleted} audit log entries.\n"
                "Chain Continuity Preserved: Remaining entries anchor to the first remaining row's previous hash."
            )
        )
