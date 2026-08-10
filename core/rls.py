"""
RLS bypass helper for management commands and admin shell operations.

Two PostgreSQL tables have FORCE ROW LEVEL SECURITY enabled:
  - audit_auditlog   (SELECT restricted to admins only)
  - records_encounter (SELECT/UPDATE restricted by hospital + treatment relationship)

Management commands run without a request context, so the per-request GUCs
(app.user_id, app.hospital_id, app.is_admin) set by RLSContextMiddleware are
not present.  Without them the policies deny all SELECT access.

Use rls_bypass() to grant read/write access to these tables from a management
command.  The context manager sets app.bypass_rls = 'on' at the session level
for the duration of the block, then resets it.

No-op on SQLite (tests / local dev without Neon).

Example:
    from core.rls import rls_bypass

    with rls_bypass():
        for entry in AuditLog.objects.order_by("pk").iterator(chunk_size=1000):
            ...

Limitation: because this app uses a single Django database role, the bypass GUC
can be set by any code with SQL execution capability.  This is protection against
accidental app-layer bugs, not against a fully compromised database connection.
"""

from contextlib import contextmanager, suppress

from django.db import connection


@contextmanager
def rls_bypass():
    """
    Context manager: set app.bypass_rls = 'on' for the duration of the block.

    Safe to call on SQLite (no-op).  Intended for management commands and any
    code that runs outside a request context.  Resets the flag in a finally
    block so the connection is safe to reuse.
    """
    if connection.vendor != "postgresql":
        yield
        return

    with connection.cursor() as cur:
        cur.execute("SELECT set_config('app.bypass_rls', 'on', false)")
    try:
        yield
    finally:
        with suppress(Exception):
            with connection.cursor() as cur:
                cur.execute("SELECT set_config('app.bypass_rls', 'off', false)")
