# ADR-009 — Consent and Legal Basis for Cross-Hospital Data Sharing

**Status:** Accepted  
**Date:** 2026-06-26

## Context

mEd stores and shares health data across participating hospitals. Health data is **sensitive personal data** under:
- **Ghana Data Protection Act, 2012 (Act 843)** — health information is a "special category" requiring heightened protection and a specific lawful basis for processing.
- **GDPR (Article 9)** — referenced as an international benchmark in the project's security analysis; the system's architecture aligns with its principles even though the deployment context is Ghanaian.

The system's defining feature — cross-hospital access to a shared patient record — must have an identifiable lawful basis beyond "the clinician asked for it."

## Decision

### Lawful basis relied on

For **same-hospital access** and **cross-hospital access under a TreatmentRelationship**: the lawful basis is **provision of healthcare / vital interests of the patient** (GDA Act 843 §28(b), analogous to GDPR Art. 9(2)(c) and (h)). A clinician treating a patient has an inherent need for the patient's medical history; the central shared record exists precisely to support this.

For **break-glass emergency access**: the basis is **vital interests** — where access is necessary to protect the life of the patient and explicit consent cannot be obtained (unconscious / incapacitated patient). Break-glass access requires a documented clinical justification, is time-limited to 1 hour, and is subject to administrator review.

For **audit and compliance access (SYSTEM_ADMIN)**: the basis is **legal obligation** and **legitimate interests** — maintaining an accurate and tamper-evident record of all PHI access is required by the system's own governance obligations and supports clinical accountability.

### What `PatientConsent` represents today

`PatientConsent` (in `access/models.py`) is a **prototype advisory layer**, not a hard access gate. It records a patient's expressed preference about data sharing with specific hospitals. It is not currently enforced by `can_access_patient()`.

The intended evolution:
1. **Phase 1 (current):** Consent is advisory. Access decisions are based on care relationships, break-glass, and same-hospital registration — reflecting the practical reality that patients cannot pre-authorize all care scenarios.
2. **Phase 2 (future):** `PatientConsent` becomes a hard gate for elective data-sharing scenarios (e.g. a patient explicitly granting a specialist hospital read access without a formal referral). Emergency access (break-glass) and vital-interests access would still override consent.
3. **Phase 3 (future):** FHIR Consent resources are exposed, enabling patients to view and manage their consent grants via a patient portal.

### Patient rights under the Ghana DPA

| Right | System support |
|---|---|
| Right to access own data | Partially: audit log records all disclosures; a patient portal is future work. |
| Right to rectification | Supported via the staff edit workflow (clinician corrects errors). |
| Right to erasure | **Incompatible with the append-only audit log** (see ADR-005). Medical records have a mandatory retention period (Ghana Health Service: 10 years). Right to erasure cannot be fulfilled for clinical records within this period; this is documented and explained to patients at registration. |
| Accounting of disclosures | The audit log is effectively an accounting of disclosures. SYSTEM_ADMIN can filter by patient NHID. |

## Consequences

- Cross-hospital access is legally grounded on care provision and vital interests, not on broad consent.
- `PatientConsent` is honest: the model exists, is populated, but is documented as advisory.
- Right-to-erasure tension is acknowledged and documented (not silently ignored).
- Future enforcement of `PatientConsent` as a hard gate is the defined path forward.
