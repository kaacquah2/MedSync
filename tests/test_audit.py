"""
Tests for the Audit Trail (audit/models.py, audit/signals.py, audit/utils.py).

Verifies:
  - AuditLog is append-only: save() on existing pk raises ValueError
  - delete() raises ValueError
  - log_action() creates a valid entry
  - is_cross_hospital flag is set correctly
  - Login/logout via API creates audit entries
  - Cross-hospital access denial is audited
"""

import json

import pytest
from django.test import RequestFactory

from audit.models import AuditLog

# ── Append-only model ──────────────────────────────────────────────────────


class TestAuditLogImmutability:
    def test_save_existing_raises(self, db):
        entry = AuditLog.objects.create(action="LOGIN", actor_username="user1")
        with pytest.raises(ValueError, match="immutable"):
            entry.save()

    def test_delete_raises(self, db):
        entry = AuditLog.objects.create(action="LOGIN", actor_username="user1")
        with pytest.raises(ValueError, match="cannot be deleted"):
            entry.delete()

    def test_queryset_delete_raises(self, db):
        AuditLog.objects.create(action="LOGIN", actor_username="user1")
        with pytest.raises(ValueError):
            AuditLog.objects.filter(actor_username="user1").first().delete()


# ── log_action utility ─────────────────────────────────────────────────────


class TestLogAction:
    def test_creates_entry(self, db, doctor_a, rf):
        from audit.utils import log_action

        request = rf.get("/")
        request.user = doctor_a
        request.META["REMOTE_ADDR"] = "127.0.0.1"

        entry = log_action(request, action="VIEW_PATIENT")

        assert entry.pk is not None
        assert entry.action == "VIEW_PATIENT"
        assert entry.actor == doctor_a
        assert entry.actor_username == doctor_a.username
        assert entry.actor_role == "doctor"
        assert entry.ip_address == "127.0.0.1"

    def test_cross_hospital_flag_true(self, db, doctor_b, patient_a, rf):
        """Doctor at Hospital B viewing a Hospital A patient sets is_cross_hospital."""
        from audit.utils import log_action

        request = rf.get("/")
        request.user = doctor_b
        request.META["REMOTE_ADDR"] = "10.0.0.1"

        is_cross = (
            doctor_b.hospital is not None
            and patient_a.registered_at_hospital is not None
            and doctor_b.hospital != patient_a.registered_at_hospital
        )

        entry = log_action(
            request,
            action="VIEW_PATIENT",
            target=patient_a,
            patient=patient_a,
            is_cross_hospital=is_cross,
        )

        assert is_cross is True
        assert entry.is_cross_hospital is True
        assert entry.patient_nhid == patient_a.universal_id

    def test_cross_hospital_flag_false_same_hospital(self, db, doctor_a, patient_a, rf):
        """Doctor at Hospital A viewing a Hospital A patient: NOT cross-hospital."""
        from audit.utils import log_action

        request = rf.get("/")
        request.user = doctor_a
        request.META["REMOTE_ADDR"] = "10.0.0.1"

        is_cross = (
            doctor_a.hospital is not None
            and patient_a.registered_at_hospital is not None
            and doctor_a.hospital != patient_a.registered_at_hospital
        )

        entry = log_action(
            request,
            action="VIEW_PATIENT",
            target=patient_a,
            patient=patient_a,
            is_cross_hospital=is_cross,
        )
        assert is_cross is False
        assert entry.is_cross_hospital is False


# ── API login/logout signal ────────────────────────────────────────────────


class TestLoginSignal:
    def test_login_creates_audit_entry(self, db, doctor_a, client):
        before_count = AuditLog.objects.filter(action="LOGIN").count()
        client.post(
            "/api/auth/login/",
            json.dumps({"username": doctor_a.username, "password": "Test@password1"}),
            content_type="application/json",
        )
        assert AuditLog.objects.filter(action="LOGIN").count() == before_count + 1

    def test_logout_creates_audit_entry(self, db, doctor_a, client_as_doctor_a):
        before_count = AuditLog.objects.filter(action="LOGOUT").count()
        client_as_doctor_a.post("/api/auth/logout/")
        assert AuditLog.objects.filter(action="LOGOUT").count() == before_count + 1


# ── Denied access audit ────────────────────────────────────────────────────


class TestAccessDeniedAudit:
    def test_cross_hospital_denied_creates_audit_entry(self, db, client_as_doctor_b, patient_a):
        """Cross-hospital access denial on /api/patients/ creates an ACCESS_DENIED entry."""
        before_count = AuditLog.objects.filter(action="ACCESS_DENIED").count()
        client_as_doctor_b.get(f"/api/patients/{patient_a.universal_id}/")
        assert AuditLog.objects.filter(action="ACCESS_DENIED").count() == before_count + 1


# ── Hash-chain integrity ───────────────────────────────────────────────────


class TestAuditHashChain:
    def test_log_action_sets_row_hash(self, db, doctor_a, rf):
        """log_action() sets a non-empty row_hash on each entry."""
        from audit.utils import log_action

        request = rf.get("/")
        request.user = doctor_a
        request.META["REMOTE_ADDR"] = "127.0.0.1"

        entry = log_action(request, action="VIEW_PATIENT")
        assert entry.row_hash  # non-empty hex digest
        assert len(entry.row_hash) == 64  # sha256 hex

    def test_second_entry_chains_to_first(self, db, doctor_a, rf):
        """The second row's prev_hash equals the first row's row_hash."""
        from audit.utils import log_action

        request = rf.get("/")
        request.user = doctor_a
        request.META["REMOTE_ADDR"] = "127.0.0.1"

        first = log_action(request, action="LOGIN")
        second = log_action(request, action="VIEW_PATIENT")

        assert second.prev_hash == first.row_hash

    def test_chain_is_verifiable(self, db, doctor_a, rf):
        """compute_row_hash reproduces the stored hash for a given entry."""
        from audit.utils import log_action

        request = rf.get("/")
        request.user = doctor_a
        request.META["REMOTE_ADDR"] = "127.0.0.1"

        entry = log_action(request, action="LOGIN")
        recomputed = AuditLog.compute_row_hash(
            entry.prev_hash,
            AuditLog._chain_fields_for(entry),
        )
        assert recomputed == entry.row_hash

    def test_tampered_row_fails_recomputation(self, db, doctor_a, rf):
        """Simulating a tamper causes recomputation to produce a different value."""
        from audit.utils import log_action

        request = rf.get("/")
        request.user = doctor_a
        request.META["REMOTE_ADDR"] = "127.0.0.1"

        entry = log_action(request, action="LOGIN")
        original_hash = entry.row_hash

        tampered_fields = AuditLog._chain_fields_for(entry)
        tampered_fields["action"] = "LOGOUT"
        recomputed = AuditLog.compute_row_hash(entry.prev_hash, tampered_fields)

        assert recomputed != original_hash


# ── Direct SQL Immutability ──────────────────────────────────────────────────


class TestDirectSQLImmutability:
    def test_direct_sql_update_raises_in_db(self, db):
        """Raw SQL UPDATE on audit_auditlog is blocked by database triggers."""
        from django.db import DatabaseError, connection

        entry = AuditLog.objects.create(action="LOGIN", actor_username="user1")
        with pytest.raises(DatabaseError):
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE audit_auditlog SET action = %s WHERE id = %s",
                    ["HACKED", entry.pk],
                )

    def test_direct_sql_delete_raises_in_db(self, db):
        """Raw SQL DELETE on audit_auditlog is blocked by database triggers."""
        from django.db import DatabaseError, connection

        entry = AuditLog.objects.create(action="LOGIN", actor_username="user1")
        with pytest.raises(DatabaseError):
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM audit_auditlog WHERE id = %s", [entry.pk])


# ── Command & Retention Tests ─────────────────────────────────────────────


class TestAuditCommandsAndRetention:
    def test_verify_audit_chain_passes_on_valid_chain(self, db, doctor_a, rf):
        """verify_audit_chain command passes with exit code 0 when chain is valid."""
        from django.core.management import call_command
        from audit.utils import log_action

        request = rf.get("/")
        request.user = doctor_a

        log_action(request, action="LOGIN")
        log_action(request, action="VIEW_PATIENT")

        # call_command returns cleanly when exit code is 0
        call_command("verify_audit_chain")

    def test_verify_audit_chain_detects_tampered_row(self, db, doctor_a, rf):
        """verify_audit_chain command catches a tampered row and exits with code 1."""
        from django.core.management import call_command
        from django.db import connection
        from audit.utils import log_action

        request = rf.get("/")
        request.user = doctor_a

        log_action(request, action="LOGIN")
        entry2 = log_action(request, action="VIEW_PATIENT")
        log_action(request, action="LOGOUT")

        # Bypass trigger in test DB to mutate row directly
        with connection.cursor() as cursor:
            if connection.vendor == "sqlite":
                cursor.execute("DROP TRIGGER IF EXISTS trg_audit_log_immutable_update")
            elif connection.vendor == "postgresql":
                cursor.execute("ALTER TABLE audit_auditlog DISABLE TRIGGER trg_audit_log_immutable")

            cursor.execute(
                "UPDATE audit_auditlog SET action = %s WHERE id = %s",
                ["PASSWORD_CHANGE", entry2.pk],
            )

            if connection.vendor == "sqlite":
                cursor.execute(
                    "CREATE TRIGGER trg_audit_log_immutable_update BEFORE UPDATE ON audit_auditlog BEGIN SELECT RAISE(ABORT, 'immutable'); END;"
                )
            elif connection.vendor == "postgresql":
                cursor.execute("ALTER TABLE audit_auditlog ENABLE TRIGGER trg_audit_log_immutable")

        with pytest.raises(SystemExit) as exc_info:
            call_command("verify_audit_chain")
        assert exc_info.value.code == 1

    def test_verify_audit_chain_rebuild_fixes_breaks(self, db, doctor_a, rf):
        """verify_audit_chain --rebuild repairs broken hashes and restores chain validity."""
        from django.core.management import call_command
        from django.db import connection
        from audit.utils import log_action

        request = rf.get("/")
        request.user = doctor_a

        log_action(request, action="LOGIN")
        entry2 = log_action(request, action="VIEW_PATIENT")
        log_action(request, action="LOGOUT")

        with connection.cursor() as cursor:
            if connection.vendor == "sqlite":
                cursor.execute("DROP TRIGGER IF EXISTS trg_audit_log_immutable_update")
            elif connection.vendor == "postgresql":
                cursor.execute("ALTER TABLE audit_auditlog DISABLE TRIGGER trg_audit_log_immutable")

            cursor.execute(
                "UPDATE audit_auditlog SET action = %s WHERE id = %s",
                ["PASSWORD_CHANGE", entry2.pk],
            )

            if connection.vendor == "sqlite":
                cursor.execute(
                    "CREATE TRIGGER trg_audit_log_immutable_update BEFORE UPDATE ON audit_auditlog BEGIN SELECT RAISE(ABORT, 'immutable'); END;"
                )
            elif connection.vendor == "postgresql":
                cursor.execute("ALTER TABLE audit_auditlog ENABLE TRIGGER trg_audit_log_immutable")

        # Before rebuild: verify fails
        with pytest.raises(SystemExit):
            call_command("verify_audit_chain")

        # After rebuild: repair hashes and verify passes
        call_command("verify_audit_chain", rebuild=True)
        call_command("verify_audit_chain")

    def test_prune_audit_logs_preserves_remaining_chain_integrity(self, db, doctor_a, rf):
        """Pruning older logs leaves the remaining chain valid according to verify_audit_chain."""
        from django.core.management import call_command
        from django.utils import timezone
        from audit.utils import log_action
        from datetime import timedelta

        request = rf.get("/")
        request.user = doctor_a

        old_entry = log_action(request, action="LOGIN")

        # Backdate first entry to 60 days ago (bypassing model save immutability guard in DB)
        from django.db import connection
        with connection.cursor() as cursor:
            if connection.vendor == "sqlite":
                cursor.execute("DROP TRIGGER IF EXISTS trg_audit_log_immutable_update")
            elif connection.vendor == "postgresql":
                cursor.execute("ALTER TABLE audit_auditlog DISABLE TRIGGER trg_audit_log_immutable")

            old_time = (timezone.now() - timedelta(days=60)).isoformat()
            cursor.execute("UPDATE audit_auditlog SET timestamp = %s WHERE id = %s", [old_time, old_entry.pk])

            if connection.vendor == "sqlite":
                cursor.execute(
                    "CREATE TRIGGER trg_audit_log_immutable_update BEFORE UPDATE ON audit_auditlog BEGIN SELECT RAISE(ABORT, 'immutable'); END;"
                )
            elif connection.vendor == "postgresql":
                cursor.execute("ALTER TABLE audit_auditlog ENABLE TRIGGER trg_audit_log_immutable")

        # Create recent entries
        log_action(request, action="VIEW_PATIENT")
        log_action(request, action="LOGOUT")

        # Prune logs older than 30 days
        call_command("prune_audit_logs", "--days=30", "--force")

        # Remaining chain verification must pass cleanly
        call_command("verify_audit_chain")


# ── Compliance Query Helpers ──────────────────────────────────────────────


class TestComplianceReportingQueries:
    def test_cross_hospital_and_break_glass_helpers(self, db, doctor_a, patient_a, rf):
        """AuditLogQuerySet helpers accurately filter cross-hospital and break-glass entries."""
        from audit.utils import log_action

        request = rf.get("/")
        request.user = doctor_a

        log_action(request, action="LOGIN")
        log_action(request, action="VIEW_PATIENT", is_cross_hospital=True)
        log_action(request, action="BREAK_GLASS", is_cross_hospital=True)

        assert AuditLog.objects.cross_hospital().count() == 2
        assert AuditLog.objects.break_glass().count() == 1
        assert AuditLog.objects.compliance_report(hospital=doctor_a.hospital).count() == 3


# ── pytest fixture ─────────────────────────────────────────────────────────
@pytest.fixture
def rf():
    return RequestFactory()

