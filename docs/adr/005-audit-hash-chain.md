# ADR-005: Audit Log Tamper Evidence — Hash Chain

**Date:** 2026-06-26
**Status:** Accepted

## Context

The audit log is the primary evidence trail for compliance and forensic investigation. A motivated insider (database administrator, compromised superuser) could potentially modify or delete rows. The Python-layer append-only guards (`save()` raises on `pk` existing; `delete()` always raises) are necessary but insufficient — they can be bypassed by direct database access.

## Decision

Implement a **SHA-256 / HMAC-SHA256 hash chain** on the `AuditLog` table with external anchoring:

- Each row stores two new fields: `prev_hash` (the `row_hash` of the immediately preceding row) and `row_hash` (computed from `prev_hash` + canonical JSON of the row's key fields).
- `row_hash = sha256(prev_hash + json.dumps(fields, sort_keys=True))` (or HMAC-SHA256 if `AUDIT_CHAIN_HMAC_KEY` is configured via external KMS/HSM) where `fields` = {actor_username, actor_role, actor_hospital, action, timestamp, target_type, target_id, patient_nhid, is_cross_hospital, ip_address, extra}.
- Computed in `audit/utils.py::log_action` — the single chokepoint — before every `save()`.
- Verification: `python manage.py verify_audit_chain` recomputes every hash, validates external anchors/ledgers, and reports breaks.
- Rebuild Safeguard: `--rebuild` permanently destroys historical tamper evidence by re-calculating hashes; it requires `--i-understand-this-destroys-tamper-evidence` and appends an immutable `REBUILD_AUDIT_CHAIN` log entry documenting the rebuild.
- External Anchors & Append-Only Ledger: `AuditLogArchiveAnchor` models and external WORM checkpoint files/ledgers (`anchor_ledger.jsonl`) prevent retroactive tampering even if an attacker attempts a chain rebuild.

Additionally, a **PostgreSQL `BEFORE UPDATE OR DELETE` trigger** (`audit/migrations/0003_auditlog_immutability_trigger.py`) raises an exception at the DB layer — a second line of defence against direct SQL modifications.

## Rationale

- A broken chain proves tampering occurred at a specific row, even if the attacker modifies the row hash to hide it (they would need to recompute the full chain from that point forward).
- Keying with HMAC (`AUDIT_CHAIN_HMAC_KEY`) ensures an attacker with shell access cannot forge valid hashes without the KMS/HSM secret key.
- External append-only anchor publishing anchors the live chain to WORM storage. Any modification to rows prior to an anchor is immediately caught during `verify_audit_chain`, even if the attacker runs `--rebuild`.
- The immutability trigger makes it significantly harder to tamper without leaving evidence visible to any monitoring process watching the PostgreSQL log.
- Both controls together provide defence-in-depth against a single point of failure.

## Limitations and known trade-offs

1. **Concurrency**: Postgres advisory transaction locks (`pg_advisory_xact_lock`) serialize chain writes across multi-worker deployments to prevent chain forks.
2. **Key custody**: When plain SHA-256 is used without an external KMS key, tamper evidence against root insiders relies on external append-only anchoring (`anchor_ledger.jsonl` / WORM checkpoints).
3. **Performance**: fetching the latest row's hash on every audit write adds one DB read. Acceptable for prototype throughput; at high volume, cache the latest hash in Redis.
