"""
Migration: PostgreSQL Row-Level Security on records_encounter (defense-in-depth).

Enables FORCE ROW LEVEL SECURITY on the encounter table.  The SELECT and UPDATE
policies mirror the application-layer can_access_patient() logic defined in
access/permissions.py:

  Priority 1: bypass — management commands (app.bypass_rls = 'on')
  Priority 2: admin  — super_admin / hospital_admin (app.is_admin = 'on')
  Priority 3: same_hospital — encounter was created at the clinician's home
              hospital (created_at_hospital_id matches app.hospital_id)
  Priority 4: treatment_relationship — an active TreatmentRelationship exists
              for this (user, patient) pair
  Priority 5: break_glass — an unexpired BreakGlassAccess grant exists for
              this (user, patient) pair

INSERT is always allowed so encounter creation (and the associated
ensure_treatment_relationship call) is never blocked.

Context for the GUCs:
  - core.middleware.RLSContextMiddleware sets app.user_id / app.hospital_id /
    app.is_admin per HTTP request.
  - core.rls.rls_bypass() sets app.bypass_rls for management commands.

Only runs on PostgreSQL — SQLite (used in tests) is skipped safely.
"""

from django.db import migrations

# The USING clause for SELECT and UPDATE is identical — factor it out.
_ACCESS_USING = """
        current_setting('app.bypass_rls',  true) = 'on'
        OR current_setting('app.is_admin', true) = 'on'
        OR created_at_hospital_id::text = current_setting('app.hospital_id', true)
        OR EXISTS (
            SELECT 1 FROM access_treatmentrelationship tr
            WHERE tr.patient_id    = records_encounter.patient_id
              AND tr.clinician_id::text = current_setting('app.user_id', true)
              AND tr.started_at <= NOW()
              AND (tr.ended_at IS NULL OR tr.ended_at > NOW())
        )
        OR EXISTS (
            SELECT 1 FROM access_breakglassaccess bg
            WHERE bg.patient_id  = records_encounter.patient_id
              AND bg.actor_id::text = current_setting('app.user_id', true)
              AND bg.expires_at  > NOW()
        )
"""

_ENABLE_SQL = f"""
ALTER TABLE records_encounter ENABLE ROW LEVEL SECURITY;
ALTER TABLE records_encounter FORCE ROW LEVEL SECURITY;

-- SELECT: mirrors can_access_patient() priority order
CREATE POLICY encounter_select ON records_encounter
    FOR SELECT
    USING (
{_ACCESS_USING}
    );

-- UPDATE: same gates as SELECT (you may only update encounters you can see)
CREATE POLICY encounter_update ON records_encounter
    FOR UPDATE
    USING (
{_ACCESS_USING}
    );

-- INSERT: always allowed (encounter creation must not be blocked)
CREATE POLICY encounter_insert ON records_encounter
    FOR INSERT
    WITH CHECK (true);
"""

_DISABLE_SQL = """
DROP POLICY IF EXISTS encounter_select ON records_encounter;
DROP POLICY IF EXISTS encounter_update ON records_encounter;
DROP POLICY IF EXISTS encounter_insert ON records_encounter;
ALTER TABLE records_encounter NO FORCE ROW LEVEL SECURITY;
ALTER TABLE records_encounter DISABLE ROW LEVEL SECURITY;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("records", "0006_patient_document"),
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
