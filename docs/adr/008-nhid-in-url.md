# ADR-008 — National Health ID in URL Paths

**Status:** Accepted  
**Date:** 2026-06-26

## Context

The patient detail, patient edit, encounter-create, and FHIR R4 endpoints identify patients via their National Health ID (NHID, format `NHID-XXXXXXXX`) in the URL path, e.g. `/patients/NHID-1A2B3C4D/`. FHIR R4 additionally requires `Patient/<identifier>` in its API surface.

The NHID is a pseudonymous identifier — it is not a name, date of birth, or directly sensitive demographic attribute. However, it is a persistent, national-scope patient identifier, and its appearance in URLs means it lands in browser history, server access logs, and potentially `Referer` headers if a page links to an external resource.

## Decision

The NHID is retained in URL paths. The following mitigations are in place:

1. **Title tags do not include the NHID.** Browser tab text and `<title>` elements use generic labels ("Patient Record — mEd"), preventing shoulder-surfing via tab titles and keeping browser history free of NHIDs.

2. **Server-side access control gates every request.** Every URL containing an NHID is protected by `@login_required` and the `can_access_patient()` gate. Knowing the NHID does not grant access; an active treatment relationship, break-glass grant, same-hospital registration, or admin privilege is additionally required. Unauthenticated requests are redirected to login.

3. **All accesses are audited.** Every view of a patient record — including failed access attempts — is written to the append-only `AuditLog` with the actor, role, hospital, IP, and cross-hospital flag. The audit log is tamper-evident via a SHA-256 hash chain.

4. **HTTPS in production.** `SESSION_COOKIE_SECURE = True` and TLS 1.3 are required in production, preventing NHID leakage via network interception.

5. **FHIR spec compliance.** The FHIR R4 specification requires `Patient/<identifier>` as the canonical resource URL. Moving to a surrogate ID here would break spec conformance; the NHID is the appropriate FHIR logical identifier for this system.

## Alternatives Considered

**Opaque surrogate (UUID) in non-FHIR routes.** Replacing NHID with a random UUID in `/patients/<uuid>/` would remove NHIDs from browser history and logs. The cost: an additional FK field and lookup join in `patients.Patient`, and rewriting all `{% url %}` reverse calls and `redirect()` calls that reference `universal_id`. The marginal security improvement is limited given controls 1–4 above and the pseudonymous nature of the NHID.

## Consequences

- NHID appears in server access logs and browser history for authenticated users who visit patient pages; access logs are treated as sensitive and access-controlled at the infrastructure level.
- Page titles are safe (no NHID). The `Referer` header risk is minimised because the app does not link out to third-party resources from patient-context pages.
- FHIR endpoints remain spec-compliant.
- If a future compliance review deems NHIDs in URLs unacceptable, the migration path is: add a `uuid` field to `Patient`, update URL patterns and lookups, keep FHIR on NHID.
