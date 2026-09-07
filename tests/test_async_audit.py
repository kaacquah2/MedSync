import pytest

from audit.models import AuditLog
from audit.utils import log_action


@pytest.mark.django_db
class TestAuditDurabilityAndContract:
    def test_log_action_writes_synchronously_and_sets_pk(self, client, db):
        """Verify that log_action immediately persists to DB and returns a saved model instance with a valid PK."""
        AuditLog.objects.all().delete()

        entry = log_action(None, action="TEST_DURABLE")

        # The returned instance must be saved with a non-null PK
        assert entry.pk is not None
        assert entry.row_hash != ""

        # The row must exist in the database immediately
        persisted = AuditLog.objects.get(pk=entry.pk)
        assert persisted.action == "TEST_DURABLE"
        assert persisted.row_hash == entry.row_hash

    def test_log_action_synchronous_regardless_of_testing_flag(
        self, client, transactional_db, settings
    ):
        """Even with settings.TESTING = False (production mode), log_action writes synchronously and durably."""
        settings.TESTING = False

        AuditLog.objects.all().delete()

        entry = log_action(None, action="TEST_PROD_DURABILITY")

        assert entry.pk is not None
        assert entry.row_hash != ""
        assert AuditLog.objects.filter(action="TEST_PROD_DURABILITY").count() == 1

        # Cleanup triggers so that pytest's transactional_db teardown/flush can run without triggering immutability constraints
        from django.db import connection

        with connection.cursor() as cursor:
            if connection.vendor == "sqlite":
                cursor.execute("DROP TRIGGER IF EXISTS trg_audit_log_immutable_delete")
                cursor.execute("DROP TRIGGER IF EXISTS trg_audit_log_immutable_update")
            elif connection.vendor == "postgresql":
                cursor.execute("ALTER TABLE audit_auditlog DISABLE TRIGGER trg_audit_log_immutable")

    def test_sequential_sync_calls_chain_correctly(self, client, db):
        """Sequential synchronous writes construct an unbroken hash chain."""
        AuditLog.objects.all().delete()

        e1 = log_action(None, action="LOGIN")
        e2 = log_action(None, action="VIEW_PATIENT")
        e3 = log_action(None, action="LOGOUT")

        assert e1.prev_hash == ""
        assert e2.prev_hash == e1.row_hash
        assert e3.prev_hash == e2.row_hash
