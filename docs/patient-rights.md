# Patient Rights — mEd EMR

## Context

mEd processes sensitive health data on behalf of patients across multiple participating hospitals. Patients have rights under the **Ghana Data Protection Act, 2012 (Act 843)** with respect to their personal data. This document maps those rights to the system's current capabilities and known limitations.

## The audit log as an accounting of disclosures

Every access to a patient record — view, search, encounter creation, diagnosis, prescription, lab result, break-glass, and access-denied events — is written to the **append-only, tamper-evident audit log** (`audit.AuditLog`). Each entry records:
- Actor (username, role, hospital)
- Action type
- Patient NHID
- Timestamp and IP address
- Whether access was cross-hospital

This audit log is functionally equivalent to an **accounting of disclosures** as required by most health-data regulations: it answers the question "who has accessed this patient's record, when, and from where."

### Admin access to disclosures

A SYSTEM_ADMIN can retrieve all audit events for a specific patient by navigating to:

```
/audit/log/?nhid=NHID-XXXXXXXX
```

Or from the patient detail page, using the **Disclosures** button (visible to SYSTEM_ADMIN only).

> **Future work:** a patient-facing portal that lets patients view their own disclosure history without requiring admin intervention.

## Patient rights mapping

| Right | Status | Notes |
|---|---|---|
| **Right to be informed** | Partial | A Privacy Notice is shown at patient registration (patient_form.html). A more comprehensive patient-facing notice is future work. |
| **Right of access** | Indirect | Clinicians can provide a patient with a summary of their record. A patient portal enabling direct access is future work. |
| **Right to rectification** | Supported | Clinicians with appropriate role can edit patient demographics (`patients:edit`) and deactivate erroneous alerts (`patients:alert_deactivate`). Clinical records (encounters, diagnoses) are append-only for audit integrity but new records can correct errors. |
| **Right to erasure** | **Not supported** | Medical records are subject to a mandatory **10-year retention period** (Ghana Health Service policy). The audit log is append-only by design (ADR-005). Right to erasure of clinical records cannot be supported within this retention window. This is disclosed to patients at registration. |
| **Right to restrict processing** | Partial | The `PatientConsent` model allows recording a patient's preference not to share with a specific hospital. This is currently advisory (not a hard access gate). Hard enforcement is future work (ADR-009). |
| **Right to data portability** | Partial | The FHIR R4 API (`/fhir/Patient/<nhid>/$everything`) exports the patient's full record as a standards-compliant Bundle, enabling portability. |
| **Accounting of disclosures** | **Supported** | The audit log records every disclosure. SYSTEM_ADMIN can retrieve per-patient disclosure history. |

## Right-to-erasure tension

The audit log's append-only immutability (enforced at both the Python and database trigger layers) directly conflicts with a right-to-erasure request for audit entries. This is a deliberate, documented design decision:
- Clinical records must be retained for legal and patient-safety reasons.
- Audit entries that record who accessed a record cannot be erased without destroying the integrity of the hash chain.
- The system design prioritises accountability and non-repudiation over erasure.

If a patient asserts a right-to-erasure claim that cannot be fulfilled, the system administrator should:
1. Document the claim and the legal basis for retention.
2. Inform the patient of the mandatory retention period.
3. Consider anonymisation of demographic fields (replacing encrypted PII with generic values) if the clinical record is no longer required, while retaining the audit trail structure.

Any such procedure must involve legal counsel and the hospital's Data Protection Officer.
