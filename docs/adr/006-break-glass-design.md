# ADR-006: Break-Glass Access Design

**Date:** 2026-06-26
**Status:** Accepted

## Context

Clinical care sometimes requires urgent access to a patient's record when no formal treatment relationship exists (e.g. a patient collapses in a corridor; an on-call doctor is covering a ward they don't normally see). Denying access in an emergency is unacceptable clinically. However, silent, unrestricted cross-hospital access is unacceptable for privacy and security.

The "break-the-glass" pattern is the established healthcare answer: allow the override, but make it deliberate, logged, time-limited, and reviewed.

## Decision

**`BreakGlassAccess` model** (`access/models.py`):
- `actor`: the clinician requesting override.
- `patient`: the patient being accessed.
- `reason`: mandatory text ≥ 20 characters (forces a genuine justification, not a one-word excuse).
- `created_at` / `expires_at`: time-boxed to `BREAK_GLASS_DURATION_HOURS` (default 1 hour).
- `mfa_reverified`: True if the clinician re-entered their TOTP code at override time.

**Flow** (`access/views.py::break_glass_request`):
1. Clinician is redirected to the access-denied interstitial (`/access-denied/<nhid>/`).
2. They choose "Break the glass" → form at `/break-glass/<nhid>/`.
3. Form requires: reason (≥ 20 chars) + acknowledge checkbox + TOTP code (when `MFA_ENFORCED=True` and device enrolled).
4. On valid submit: `BreakGlassAccess` created; `BREAK_GLASS` audit entry written with reason + expires_at + mfa_reverified; redirect to patient record with a persistent warning banner.
5. After `expires_at`: `can_access_patient()` no longer finds an active grant; next access attempt re-triggers the gate.

**Audit visibility**: `BREAK_GLASS` entries are first-class audit events, queryable by `?action=BREAK_GLASS` in the audit log view (SYSTEM_ADMIN). An admin dashboard could surface all break-glass events for review.

## Design rationale

- **Never silent**: every override is logged with actor, patient, reason, and expiry. There is no way to access a patient cross-hospital without generating an audit entry.
- **Time-boxed**: a 1-hour grant means the clinician can complete their immediate clinical task, but ongoing care must establish a proper `TreatmentRelationship`.
- **Re-MFA**: re-entering the TOTP code confirms the clinician is physically present at the device. This control is conditional on device enrolment to avoid locking out emergency care; unenrolled clinicians receive access with `mfa_reverified=False`.
- **Reason requirement**: ≥ 20 chars makes it impossible to type a trivially short justification; the reason is stored and audited, not discarded.

## Consequences

- Receptionists and LAB_TECHs cannot currently initiate break-glass (the form is `@login_required` but the access gate is also applied to clinical sub-views). The design could be extended to allow non-clinical roles.
- A missed audit (e.g. due to a race condition or application crash mid-save) would leave a `BreakGlassAccess` row but no audit row. Production would use a DB transaction wrapping both saves.

## What a real production deployment would add

- Real-time alert (email/SMS/Slack) to the patient's primary doctor and hospital admin when break-glass is triggered.
- Mandatory post-override documentation (clinical justification attached to the encounter).
- Configurable duration per role (e.g. 2 hours for emergency medicine, 30 minutes for admin override).
- Workflow for formal retrospective review with sign-off by a supervisor.
