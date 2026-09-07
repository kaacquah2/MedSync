"""
Management command: anchor the current audit log hash chain to external append-only storage.

Usage:
    python manage.py anchor_audit_chain
"""

from django.core.management.base import BaseCommand

from audit.anchors import create_live_anchor
from audit.models import AuditLog, AuditLogArchiveAnchor
from core.rls import rls_bypass


class Command(BaseCommand):
    help = "Anchor the current audit log chain tip to external append-only storage."

    def handle(self, *args, **options):
        with rls_bypass():
            last_entry = AuditLog.objects.order_by("-pk").first()
            if not last_entry:
                self.stdout.write(self.style.WARNING("No audit logs found to anchor."))
                return

            latest_anchor = AuditLogArchiveAnchor.objects.filter(
                last_row_pk__gte=last_entry.pk
            ).first()
            if latest_anchor:
                self.stdout.write(
                    self.style.NOTICE(
                        f"Current tip (PK={last_entry.pk}) is already anchored in '{latest_anchor.archive_filename}'."
                    )
                )
                return

            anchor = create_live_anchor()
            if anchor:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Successfully anchored audit chain tip: PK={anchor.last_row_pk}, "
                        f"hash={anchor.last_row_hash[:12]}… to '{anchor.archive_filename}'."
                    )
                )
            else:
                self.stdout.write(self.style.WARNING("Could not create anchor."))
