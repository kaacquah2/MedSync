"""
Migration: PostgreSQL trigger enforcing audit log immutability at the DB level.

Guards against application-layer bugs that bypass the Python-level save()/delete()
guards.  Only runs on PostgreSQL — SQLite (used in tests) is skipped safely.

The trigger raises an exception on any UPDATE or DELETE attempt on audit_auditlog,
regardless of which database role issues the query.  Paired with a least-privilege
app role that has no UPDATE/DELETE grant on the table (see docs/security-analysis.md).
"""

from django.db import migrations

_CREATE_TRIGGER_SQL = """
CREATE OR REPLACE FUNCTION audit_log_immutability()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION
        'audit_auditlog is immutable: UPDATE and DELETE are prohibited. '
        'TG_OP=%, row id=%',
        TG_OP, OLD.id;
    RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS trg_audit_log_immutable ON audit_auditlog;

CREATE TRIGGER trg_audit_log_immutable
BEFORE UPDATE OR DELETE ON audit_auditlog
FOR EACH ROW EXECUTE FUNCTION audit_log_immutability();
"""

_DROP_TRIGGER_SQL = """
DROP TRIGGER IF EXISTS trg_audit_log_immutable ON audit_auditlog;
DROP FUNCTION IF EXISTS audit_log_immutability();
"""


_SQLITE_CREATE_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS trg_audit_log_immutable_update
BEFORE UPDATE ON audit_auditlog
BEGIN
    SELECT RAISE(ABORT, 'audit_auditlog is immutable: UPDATE prohibited');
END;

CREATE TRIGGER IF NOT EXISTS trg_audit_log_immutable_delete
BEFORE DELETE ON audit_auditlog
BEGIN
    SELECT RAISE(ABORT, 'audit_auditlog is immutable: DELETE prohibited');
END;
"""

_SQLITE_DROP_TRIGGERS = """
DROP TRIGGER IF EXISTS trg_audit_log_immutable_update;
DROP TRIGGER IF EXISTS trg_audit_log_immutable_delete;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("audit", "0002_auditlog_prev_hash_auditlog_row_hash_and_more"),
    ]

    operations = [
        migrations.RunSQL(
            sql=_CREATE_TRIGGER_SQL,
            reverse_sql=_DROP_TRIGGER_SQL,
            hints={"target_db": "postgresql"},
        ),
    ]

    def apply(self, project_state, schema_editor, collect_sql=False):
        if schema_editor.connection.vendor == "postgresql":
            return super().apply(project_state, schema_editor, collect_sql)
        elif schema_editor.connection.vendor == "sqlite":
            with schema_editor.connection.cursor() as cursor:
                cursor.executescript(_SQLITE_CREATE_TRIGGERS)
            return project_state
        return project_state

    def unapply(self, project_state, schema_editor, collect_sql=False):
        if schema_editor.connection.vendor == "postgresql":
            return super().unapply(project_state, schema_editor, collect_sql)
        elif schema_editor.connection.vendor == "sqlite":
            with schema_editor.connection.cursor() as cursor:
                cursor.executescript(_SQLITE_DROP_TRIGGERS)
            return project_state
        return project_state
