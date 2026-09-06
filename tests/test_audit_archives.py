import os
import shutil
import json
import pytest
from django.core.management import call_command
from django.utils import timezone
from datetime import timedelta
from django.conf import settings
from audit.models import AuditLog, AuditLogArchiveAnchor
from core.rls import rls_bypass

@pytest.mark.django_db
class TestAuditArchives:
    @pytest.fixture(autouse=True)
    def setup_cleanup_media(self):
        # Create a temp media root for testing
        old_media_root = settings.MEDIA_ROOT
        settings.MEDIA_ROOT = os.path.join(settings.BASE_DIR, "test_media")
        os.makedirs(settings.MEDIA_ROOT, exist_ok=True)
        yield
        # Cleanup
        if os.path.exists(settings.MEDIA_ROOT):
            shutil.rmtree(settings.MEDIA_ROOT)
        settings.MEDIA_ROOT = old_media_root

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
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            data = json.loads(content)
            assert len(data) == 2
            assert data[0]["actor_username"] == "user_1"
            assert data[1]["actor_username"] == "user_2"

            # Execute chain verification command
            # It should succeed and return exit code 0
            try:
                call_command("verify_audit_chain", verbose=True)
            except SystemExit as e:
                assert e.code == 0
