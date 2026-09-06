import queue
import time
import pytest
from django.conf import settings
from audit.models import AuditLog
from audit.utils import log_action, _audit_queue

@pytest.mark.django_db
class TestAsyncAuditLogging:
    def test_synchronous_logging_in_tests(self, client, db):
        # By default in tests, settings.TESTING = True
        assert getattr(settings, "TESTING", False) is True
        
        # Clear database and queue
        AuditLog.objects.all().delete()
        while not _audit_queue.empty():
            try:
                _audit_queue.get_nowait()
                _audit_queue.task_done()
            except queue.Empty:
                break
                
        # Write log
        entry = log_action(None, action="TEST_SYNC")
        
        # In testing mode, it should be immediately in the DB
        assert AuditLog.objects.filter(action="TEST_SYNC").count() == 1
        assert entry.row_hash != ""

    def test_asynchronous_logging(self, client, transactional_db, settings):
        # Force async by temporarily toggling TESTING = False
        settings.TESTING = False
        
        AuditLog.objects.all().delete()
        while not _audit_queue.empty():
            try:
                _audit_queue.get_nowait()
                _audit_queue.task_done()
            except queue.Empty:
                break
                
        # Trigger async log
        entry = log_action(None, action="TEST_ASYNC")
        
        # Wait a short moment for the background worker to consume and write
        _audit_queue.join()
        
        # Should now be written to the DB
        assert AuditLog.objects.filter(action="TEST_ASYNC").count() == 1

        # Cleanup triggers so that pytest's transactional_db teardown/flush can run without triggering immutability constraints
        from django.db import connection
        with connection.cursor() as cursor:
            if connection.vendor == "sqlite":
                cursor.execute("DROP TRIGGER IF EXISTS trg_audit_log_immutable_delete")
                cursor.execute("DROP TRIGGER IF EXISTS trg_audit_log_immutable_update")

