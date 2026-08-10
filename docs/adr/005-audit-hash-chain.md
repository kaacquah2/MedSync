# ADR-005: Audit Log Tamper Evidence — Hash Chain

**Date:** 2026-06-26
**Status:** Accepted

## Context

The audit log is the primary evidence trail for compliance and forensic investigation. A motivated insider (database administrator, compromised superuser) could potentially modify or delete rows. The Python-layer append-only guards (`save()` raises on `pk` existing; `delete()` always raises) are necessary but insufficient — they can be bypassed by direct database access.

## Decision

Implement a **SHA-256 hash chain** on the `AuditLog` table:

- Each row stores two new fields: `prev_hash` (the `row_hash` of the immediately preceding row) and `row_hash` (computed from `prev_hash` + canonical JSON of the row's key fields).
- `row_hash = sha256(prev_hash + json.dumps(fields, sort_keys=True))` where `fields` = {actor_username, action, timestamp, target_type, target_id, patient_nhid, is_cross_hospital, ip_address}.
- Computed in `audit/utils.py::log_action` — the single chokepoint — before every `save()`.
- Verification: `python manage.py verify_audit_chain` recomputes every hash and reports the first break.

Additionally, a **PostgreSQL `BEFORE UPDATE OR DELETE` trigger** (`audit/migrations/0003_auditlog_immutability_trigger.py`) raises an exception at the DB layer — a second line of defence against direct SQL modifications.

## Rationale

- A broken chain proves tampering occurred at a specific row, even if the attacker modifies the row hash to hide it (they would need to recompute the full chain from that point forward).
- The trigger makes it significantly harder to tamper without leaving evidence visible to any monitoring process watching the PostgreSQL log.
- Both controls together provide defence-in-depth against a single point of failure.

## Limitations and known trade-offs

1. **Concurrency**: the current implementation uses `ORDER BY -pk` to find the previous hash. Under concurrent writes, two rows could race and both compute the same `prev_hash`. This creates a **chain fork** (two rows pointing to the same predecessor) rather than a linear chain. For the single-instance prototype, the risk is low. Production would use a DB-level sequence or `SELECT ... FOR UPDATE` advisory lock.
2. **No external anchor**: the chain does not currently publish its tip to an external timestamping authority (RFC 3161). A sufficiently powerful attacker who controls the DB could rebuild the entire chain. External anchoring (blockchain timestamp, trusted notary) is left as a production enhancement.
3. **Performance**: fetching the latest row's hash on every audit write adds one DB read. Acceptable for prototype throughput; at high volume, cache the latest hash in Redis.

## What a real production deployment would add

- Serialised chain writes via an advisory lock or dedicated Celery task queue.
- External RFC 3161 timestamping of daily chain digests.
- Time-partitioned audit table (`audit_auditlog_2026q1`, etc.) with a verification checkpoint per partition.
- Sentry/SIEM alert on any `verify_audit_chain` failure.
