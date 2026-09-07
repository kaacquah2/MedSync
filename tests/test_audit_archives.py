import json
import os
from datetime import timedelta

import pytest
from django.conf import settings
from django.core.management import call_command
from django.utils import timezone

from audit.models import AuditLog, AuditLogArchiveAnchor
from core.rls import rls_bypass


@pytest.mark.django_db
class TestAuditArchives:
    def test_prune_and_verify_chain(self):
        # Disable RLS bypass or use rls_bypass context to write
        with rls_bypass():
            AuditLog.objects.all().delete()
            AuditLogArchiveAnchor.objects.all().delete()

            # Create 3 sequential logs
            prev_hash = ""
            days_ago = [40, 30, 10]
            for i, d in enumerate(days_ago, 1):
                entry = AuditLog(
                    actor_username=f"user_{i}",
                    action=f"ACTION_{i}",
                    timestamp=timezone.now() - timedelta(days=d),
                    extra={},
                )
                fields = AuditLog._chain_fields_for(entry)
                entry.prev_hash = prev_hash
                entry.row_hash = AuditLog.compute_row_hash(prev_hash, fields)
                entry.save()
                prev_hash = entry.row_hash

            # Make sure we have 3 logs
            assert AuditLog.objects.count() == 3

            # Prune logs older than 25 days (should prune index 1 and 2, keeping index 3)
            # We call prune command with --days=25 and --force (no prompt)
            call_command("prune_audit_logs", days=25, force=True)

            # Assert database has only 1 log left (the youngest one)
            assert AuditLog.objects.count() == 1

            # Assert a WORM archive anchor was created
            assert AuditLogArchiveAnchor.objects.count() == 1
            anchor = AuditLogArchiveAnchor.objects.first()
            assert anchor.last_row_pk == 2

            # Assert WORM archive file exists
            archive_dir = os.path.join(settings.MEDIA_ROOT, "audit_archives")
            file_path = os.path.join(archive_dir, anchor.archive_filename)
            assert os.path.exists(file_path)

            # Verify file contents are valid JSON and matches the hash
            with open(file_path, encoding="utf-8") as f:
                content = f.read()
            data = json.loads(content)
            assert len(data) == 2
            assert data[0]["actor_username"] == "user_1"
            assert data[1]["actor_username"] == "user_2"

            # Verify ledger file exists and contains the anchor
            from audit.anchors import get_anchor_ledger_path, read_anchor_ledger

            ledger_path = get_anchor_ledger_path()
            assert os.path.exists(ledger_path)
            ledger_entries = read_anchor_ledger()
            assert len(ledger_entries) == 1
            assert ledger_entries[0]["last_row_pk"] == 2

            # Execute chain verification command
            # It should succeed and return exit code 0
            try:
                call_command("verify_audit_chain", verbose=True)
            except SystemExit as e:
                assert e.code == 0

    def test_anchor_audit_chain_and_verify_anchor_flag(self):
        with rls_bypass():
            AuditLog.objects.all().delete()
            AuditLogArchiveAnchor.objects.all().delete()

            # Create 2 logs
            prev = ""
            for i in range(1, 3):
                entry = AuditLog(
                    actor_username=f"dr_{i}", action="LOGIN", timestamp=timezone.now(), extra={}
                )
                fields = AuditLog._chain_fields_for(entry)
                entry.prev_hash = prev
                entry.row_hash = AuditLog.compute_row_hash(prev, fields)
                entry.save()
                prev = entry.row_hash

        # Run anchor_audit_chain command
        call_command("anchor_audit_chain")

        # Verify anchor was created
        with rls_bypass():
            assert AuditLogArchiveAnchor.objects.count() == 1
            anchor = AuditLogArchiveAnchor.objects.first()
            assert anchor.last_row_pk == 2

        # Verify chain passes with --anchor flag (no duplicate anchor created)
        call_command("verify_audit_chain", anchor=True)
        with rls_bypass():
            assert AuditLogArchiveAnchor.objects.count() == 1

        # Add 3rd log and run verify with --anchor
        with rls_bypass():
            entry3 = AuditLog(
                actor_username="dr_3", action="LOGOUT", timestamp=timezone.now(), extra={}
            )
            fields = AuditLog._chain_fields_for(entry3)
            entry3.prev_hash = prev
            entry3.row_hash = AuditLog.compute_row_hash(prev, fields)
            entry3.save()

        call_command("verify_audit_chain", anchor=True)
        with rls_bypass():
            assert AuditLogArchiveAnchor.objects.count() == 2
            latest = AuditLogArchiveAnchor.objects.order_by("-last_row_pk").first()
            assert latest.last_row_pk == entry3.pk

    def test_external_anchor_prevents_tampering_via_rebuild(self):
        from django.db import connection

        with rls_bypass():
            AuditLog.objects.all().delete()
            AuditLogArchiveAnchor.objects.all().delete()

            # Create 3 logs
            prev = ""
            for i in range(1, 4):
                entry = AuditLog(
                    actor_username=f"doc_{i}", action="LOGIN", timestamp=timezone.now(), extra={}
                )
                fields = AuditLog._chain_fields_for(entry)
                entry.prev_hash = prev
                entry.row_hash = AuditLog.compute_row_hash(prev, fields)
                entry.save()
                prev = entry.row_hash

        # Anchor chain tip at row 3
        call_command("anchor_audit_chain")

        # Now tamper with row 2 using direct SQL
        with connection.cursor() as cursor:
            if connection.vendor == "sqlite":
                cursor.execute("DROP TRIGGER IF EXISTS trg_audit_log_immutable_update")
            elif connection.vendor == "postgresql":
                cursor.execute("ALTER TABLE audit_auditlog DISABLE TRIGGER trg_audit_log_immutable")

            cursor.execute("UPDATE audit_auditlog SET action = %s WHERE id = %s", ["TAMPERED", 2])

            if connection.vendor == "sqlite":
                cursor.execute(
                    "CREATE TRIGGER trg_audit_log_immutable_update BEFORE UPDATE ON audit_auditlog BEGIN SELECT RAISE(ABORT, 'immutable'); END;"
                )
            elif connection.vendor == "postgresql":
                cursor.execute("ALTER TABLE audit_auditlog ENABLE TRIGGER trg_audit_log_immutable")

        # Re-seal the chain using --rebuild with explicit flag
        call_command(
            "verify_audit_chain", rebuild=True, i_understand_this_destroys_tamper_evidence=True
        )

        # Rebuilding recomputed internal hashes, BUT external anchor at row 3 still holds previous hash!
        # verify_audit_chain MUST detect the anchor mismatch!
        with pytest.raises(SystemExit) as exc:
            call_command("verify_audit_chain")
        assert exc.value.code == 1

    def test_ledger_tampering_detected(self):
        with rls_bypass():
            AuditLog.objects.all().delete()
            AuditLogArchiveAnchor.objects.all().delete()

            entry = AuditLog(
                actor_username="admin", action="LOGIN", timestamp=timezone.now(), extra={}
            )
            fields = AuditLog._chain_fields_for(entry)
            entry.row_hash = AuditLog.compute_row_hash("", fields)
            entry.save()

        call_command("anchor_audit_chain")

        # Delete database anchor row behind the scenes
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM audit_auditlogarchiveanchor")

        # verify_audit_chain reads append-only ledger, notices DB anchor missing, and fails
        with pytest.raises(SystemExit) as exc:
            call_command("verify_audit_chain")
        assert exc.value.code == 1

    def test_anchor_model_immutability(self):
        anchor = AuditLogArchiveAnchor.objects.create(
            archive_filename="test_anchor.json",
            last_row_pk=1,
            last_row_hash="abc123hash",
            archive_file_hash="def456filehash",
        )
        # Attempting save on existing PK raises ValueError
        with pytest.raises(ValueError, match="immutable"):
            anchor.save()

        # Attempting delete raises ValueError
        with pytest.raises(ValueError, match="cannot be deleted"):
            anchor.delete()

    def test_hmac_keyed_chain_computation(self, monkeypatch):
        fields = {"actor_username": "secure_user", "action": "LOGIN"}
        unkeyed_hash = AuditLog.compute_row_hash("prev_test", fields)

        # Set an HMAC key
        monkeypatch.setattr(
            settings, "AUDIT_CHAIN_HMAC_KEY", "super-secret-kms-key-12345", raising=False
        )
        keyed_hash = AuditLog.compute_row_hash("prev_test", fields)

        assert keyed_hash != unkeyed_hash
        assert len(keyed_hash) == 64  # SHA256 hex length
