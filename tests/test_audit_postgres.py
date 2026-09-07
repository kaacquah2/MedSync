"""
Postgres-backed integration tests for the Audit Trail hash chain under Row-Level Security (RLS).

Background:
    audit/migrations/0010_auditlog_rls.py enables FORCE ROW LEVEL SECURITY on audit_auditlog:
      - audit_select: SELECT allowed only when app.is_admin = 'on' or app.bypass_rls = 'on'
      - audit_insert: INSERT always allowed
    RLSContextMiddleware sets app.is_admin on the HTTP request thread's connection.
    When log_action runs, it executes under rls_bypass() so that reading the last row's
    prev_hash succeeds even in sessions without app.is_admin set.

This test module verifies:
    1. Direct PostgreSQL RLS enforcement: SELECT is blocked without bypass/admin GUCs.
    2. log_action under PostgreSQL RLS correctly chains hashes across consecutive rows
       when wrapped in rls_bypass().
    3. verify_audit_chain management command successfully validates the resulting chain.
    4. Unit-level assertion that log_action always invokes rls_bypass (runs on all backends).
"""

import pytest
from django.conf import settings
from django.core.management import call_command
from django.db import connection

from audit.models import AuditLog
from audit.utils import log_action
from core.rls import rls_bypass


@pytest.mark.django_db(transaction=True)
class TestAuditPostgresRLSIntegration:
    @pytest.fixture(autouse=True)
    def require_postgresql(self):
        if connection.vendor != "postgresql":
            pytest.skip("Test requires a PostgreSQL database with Row-Level Security (RLS) enabled")

    def _clear_logs(self):
        with rls_bypass():
            AuditLog.objects.all().delete()

    def test_rls_blocks_select_without_bypass_or_admin(self):
        """Under FORCE ROW LEVEL SECURITY, SELECT returns 0 rows if neither GUC is set."""
        self._clear_logs()

        # Insert an entry directly (INSERT is permitted by audit_insert policy)
        with rls_bypass():
            AuditLog.objects.create(
                action="MANUAL_INSERT",
                actor_username="attacker",
                row_hash="test_hash_genesis",
            )

        # Ensure GUCs on the current connection are unset/off
        with connection.cursor() as cur:
            cur.execute("SELECT set_config('app.is_admin', 'off', false)")
            cur.execute("SELECT set_config('app.bypass_rls', 'off', false)")

        # Querying without bypass or admin GUC should return empty queryset due to RLS
        visible_count = AuditLog.objects.count()
        assert visible_count == 0, (
            "RLS policy audit_select should deny SELECT when app.is_admin and app.bypass_rls are off"
        )

        # Querying with rls_bypass should succeed and reveal the row
        with rls_bypass():
            visible_with_bypass = AuditLog.objects.count()
            assert visible_with_bypass == 1

        # Disable immutable trigger for teardown
        with connection.cursor() as cursor:
            cursor.execute("ALTER TABLE audit_auditlog DISABLE TRIGGER trg_audit_log_immutable")

    def test_log_action_chains_hashes_under_postgres_rls(self, monkeypatch):
        """
        log_action executes under rls_bypass() and advisory lock. It must successfully
        read the previous entry's row_hash and construct an unbroken hash chain.
        """
        self._clear_logs()
        monkeypatch.setattr(settings, "TESTING", False)

        # Dispatch three sequential actions synchronously
        e1 = log_action(None, action="LOGIN", extra={"step": 1})
        e2 = log_action(None, action="VIEW_PATIENT", extra={"step": 2})
        e3 = log_action(None, action="LOGOUT", extra={"step": 3})

        assert e1.pk is not None
        assert e2.pk is not None
        assert e3.pk is not None

        # Read back all entries using rls_bypass
        with rls_bypass():
            logs = list(AuditLog.objects.order_by("pk"))
            assert len(logs) == 3, f"Expected 3 audit logs in database, found {len(logs)}"

            # Genesis row
            assert logs[0].prev_hash == ""
            assert logs[0].row_hash != ""

            # Row 2 must link to Row 1
            assert logs[1].prev_hash == logs[0].row_hash, (
                f"Hash chain broken at row 2! prev_hash is {logs[1].prev_hash!r}, "
                f"expected row 1 row_hash {logs[0].row_hash!r}. "
                "This indicates log_action could not read previous row due to Postgres RLS."
            )
            assert logs[1].row_hash != ""

            # Row 3 must link to Row 2
            assert logs[2].prev_hash == logs[1].row_hash, (
                f"Hash chain broken at row 3! prev_hash is {logs[2].prev_hash!r}, "
                f"expected row 2 row_hash {logs[1].row_hash!r}."
            )
            assert logs[2].row_hash != ""

            # Verify that verify_audit_chain management command reports intact chain
            call_command("verify_audit_chain")

        # Cleanup trigger for test isolation
        with connection.cursor() as cursor:
            cursor.execute("ALTER TABLE audit_auditlog DISABLE TRIGGER trg_audit_log_immutable")


@pytest.mark.django_db(transaction=True)
class TestAuditWorkerRLSBypassUnit:
    """
    Backend-agnostic test verifying that log_action explicitly wraps
    database read and write operations in rls_bypass().
    """

    def test_log_action_invokes_rls_bypass(self, monkeypatch):
        monkeypatch.setattr(settings, "TESTING", False)

        bypass_called = False
        import core.rls

        original_rls_bypass = core.rls.rls_bypass

        from contextlib import contextmanager

        @contextmanager
        def tracking_rls_bypass():
            nonlocal bypass_called
            bypass_called = True
            with original_rls_bypass():
                yield

        monkeypatch.setattr("audit.utils.rls_bypass", tracking_rls_bypass)

        log_action(None, action="UNIT_TEST_RLS_CHECK")

        assert bypass_called is True, "log_action must call rls_bypass() around read+write"

        from django.db import connection

        with connection.cursor() as cursor:
            if connection.vendor == "sqlite":
                cursor.execute("DROP TRIGGER IF EXISTS trg_audit_log_immutable_delete")
                cursor.execute("DROP TRIGGER IF EXISTS trg_audit_log_immutable_update")
            elif connection.vendor == "postgresql":
                cursor.execute("ALTER TABLE audit_auditlog DISABLE TRIGGER trg_audit_log_immutable")
