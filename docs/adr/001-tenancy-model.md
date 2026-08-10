# ADR-001: Tenancy Model — Shared Schema, Central Patient Registry

**Date:** 2026-06-26
**Status:** Accepted

## Context

The system must serve multiple participating hospitals ("tenants") from a single database. Two broad strategies exist:
1. **Schema-per-tenant** — each hospital gets a separate PostgreSQL schema.
2. **Shared schema with tenant column** — all data in one schema; rows carry a `hospital_id` discriminator.

Additionally, the core purpose of the system — **inter-hospital patient record sharing** — means patients themselves are NOT siloed by hospital. A patient registered at Hospital A must be visible (with appropriate authorisation) to a doctor at Hospital B.

## Decision

Use a **shared schema** with the following design:
- **Users and Staff** carry a `hospital` FK — they belong to exactly one hospital (or null for SYSTEM_ADMIN).
- **Hospitals** are first-class entities (`hospitals.Hospital`).
- **Patients** are **central/shared** — they do not belong to a single hospital. They are identified by a universal NHID.
- **Encounters and clinical records** carry a `created_at_hospital` FK for provenance, but are not access-restricted by that FK alone.
- **Access control** is expressed by `TreatmentRelationship` and `BreakGlassAccess` at the application layer, not by data isolation.

## Rationale

- **Simpler than schema-per-tenant** for a student prototype; Django's ORM handles all tenant-related filtering.
- **Matches the domain**: the whole point of a centralized EMR is that the patient is visible across hospitals. Hiding patients behind tenant walls would defeat the purpose.
- **Access control at the right layer**: `can_access_patient()` is a semantic gate (treatment relationship + consent) that reflects clinical reality, not a data isolation primitive.

## Consequences

- Application code must be audited to ensure every PHI query is properly filtered (either by hospital context for staff views, or by access gate for patient views).
- Cross-tenant data leaks are prevented at the application layer, with PostgreSQL RLS as a defence-in-depth option for the audit log (see ADR-002).
- A schema-per-tenant migration would require significant Django multi-db work — document as a future option if regulatory requirements mandate stronger isolation.

## What a real production deployment would add

- ~~PostgreSQL RLS on `audit_auditlog` and `encounters` as database-level defence-in-depth.~~
  **Implemented** — `audit/migrations/0010_auditlog_rls.py` and `records/migrations/0007_encounter_rls.py`
  enable `FORCE ROW LEVEL SECURITY` on both tables.  Per-request GUCs are set by
  `core.middleware.RLSContextMiddleware`.  Management commands use `core.rls.rls_bypass()`.
  **Limitation:** the app uses a single DB role, so this protects against app-layer query bugs
  and most SQL injection but not against a fully compromised role.  See `docs/security-analysis.md §5a`.
- Regular automated scans to detect unscoped queries (static analysis rule).
