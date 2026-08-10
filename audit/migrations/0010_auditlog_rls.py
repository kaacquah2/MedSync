"""
Migration: PostgreSQL Row-Level Security on audit_auditlog (defense-in-depth).

Enables FORCE ROW LEVEL SECURITY on the audit log table so that even the
table owner (the Django application role) is subject to the policies.

Policies:
  audit_select  — SELECT only when app.is_admin = 'on' or app.bypass_rls = 'on'
  audit_insert  — INSERT always allowed (log_action must never be blocked)

No UPDATE/DELETE policies are added.  UPDATE and DELETE are denied by default
when no matching policy exists, and are also blocked by the existing immutability
trigger (0003_auditlog_immutability_trigger).

Context for the GUCs:
  - core.middleware.RLSContextMiddleware sets app.is_admin per HTTP request.
  - core.rls.rls_bypass() sets app.bypass_rls for management commands.

Only runs on PostgreSQL — SQLite (used in tests) is skipped safely.
"""

from django.db import migrations

_ENABLE_SQL = """
ALTER TABLE audit_auditlog ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_auditlog FORCE ROW LEVEL SECURITY;

-- SELECT: admin users only, or explicit management-command bypass
CREATE POLICY audit_select ON audit_auditlog
    FOR SELECT
    USING (
        current_setting('app.is_admin',   true) = 'on'
        OR current_setting('app.bypass_rls', true) = 'on'
    );

-- INSERT: always allowed so log_action() never fails
CREATE POLICY audit_insert ON audit_auditlog
    FOR INSERT
    WITH CHECK (true);
"""

_DISABLE_SQL = """
DROP POLICY IF EXISTS audit_select ON audit_auditlog;
DROP POLICY IF EXISTS audit_insert ON audit_auditlog;
ALTER TABLE audit_auditlog NO FORCE ROW LEVEL SECURITY;
ALTER TABLE audit_auditlog DISABLE ROW LEVEL SECURITY;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("audit", "0009_add_document_handover_actions"),
    ]

    operations = [
        migrations.RunSQL(
            sql=_ENABLE_SQL,
            reverse_sql=_DISABLE_SQL,
            hints={"target_db": "postgresql"},
        ),
    ]

    def apply(self, project_state, schema_editor, collect_sql=False):
        if schema_editor.connection.vendor != "postgresql":
            # Skip gracefully on SQLite (tests) and other non-Postgres backends
            return project_state
        return super().apply(project_state, schema_editor, collect_sql)

    def unapply(self, project_state, schema_editor, collect_sql=False):
        if schema_editor.connection.vendor != "postgresql":
            return project_state
        return super().unapply(project_state, schema_editor, collect_sql)
