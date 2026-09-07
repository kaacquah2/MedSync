# Break-Glass Review Process

## Purpose

Break-glass (emergency record access without a formal treatment relationship) is a legitimate and necessary safety valve in an inter-hospital EMR. Its legitimacy rests entirely on the credible threat of review — an unreviewed break-glass provides no deterrence against misuse.

This document defines the review process, cadence, owner, and escalation path.

## System behaviour

When a clinician invokes break-glass:
1. They must provide a clinical justification (minimum 20 characters).
2. They must tick an acknowledgement that the access "is logged and will be reviewed."
3. **Conditional MFA re-verification**: If MFA is enforced (`settings.MFA_ENFORCED=True`) *and* the user has an enrolled, confirmed TOTP device, they must re-verify their identity with a valid TOTP code. **This control is conditional, not unconditional:** if a clinician has not yet enrolled a TOTP device, re-verification is skipped and emergency access is granted with `mfa_reverified=False` so life-critical care is never obstructed. Consequently, a clinician who has not enrolled TOTP can reach emergency access without second-factor re-verification.
4. A `BREAK_GLASS` audit log entry is written immediately with: actor, role, hospital, patient NHID, reason text, expiry time, IP address, cross-hospital flag, and `mfa_reverified` boolean.
5. Access is time-limited to **1 hour**.

## Review access

The SYSTEM_ADMIN role has access to the full audit trail. Break-glass events are filtered by navigating to:

```
/audit/log/?action=BREAK_GLASS
```

Or from the Audit Log page: select **Action = "Break-Glass Override"** and click Filter.

Each row shows: actor, their role and hospital, the patient NHID, the timestamp, and the IP address. The `extra` JSON field records the reason text and expiry. The `BreakGlassAccess` record tracks `mfa_reverified` (`True` if TOTP was verified at point of override, `False` if skipped due to no enrolled device or disabled MFA).

## Review cadence and owner

| Role | Responsibility | Cadence |
|---|---|---|
| **SYSTEM_ADMIN** | Periodic review of all break-glass events across all hospitals | Weekly (or within 24 h of a flagged event) |
| **HOSPITAL_ADMIN** | Review of break-glass events by staff at their own hospital | Monthly compliance check |

**Minimum standard:** every break-glass event must be reviewed within **5 working days**. Events that cannot be explained by the justification provided should be escalated.

## Escalation

| Scenario | Action |
|---|---|
| Justification is blank, vague ("emergency"), or clearly pretextual | Contact the clinician's line manager; flag to the hospital's Data Protection Officer. |
| Repeated access to the same patient by the same clinician without a formal referral | Establish whether a TreatmentRelationship should be opened; investigate for policy breach. |
| Access outside normal working hours with no documented emergency | Escalate to HOSPITAL_ADMIN and, if unresolved, to the Ghana Data Protection Commission. |
| Break-glass with `mfa_reverified=False` under an MFA-enforced policy | Investigate whether the clinician avoided TOTP enrolment to bypass re-verification; mandate immediate device enrolment. |

## Audit log integrity

The audit log is append-only and tamper-evident (SHA-256 hash chain — see ADR-005). Break-glass entries cannot be deleted or modified. The hash chain should be verified regularly:

```bash
python manage.py verify_audit_chain
```

## Optional: automated flagging (future work)

A future improvement would be an automated email/in-app notification to HOSPITAL_ADMIN on each break-glass event at their hospital, eliminating the need for periodic manual checks. The audit infrastructure already produces the necessary data; the missing piece is a notification dispatch from the `BREAK_GLASS` audit signal.
