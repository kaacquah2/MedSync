# Patient Rights — mEd EMR

## Context & Statutory Lawful Basis (Act 843)

mEd processes and exchanges sensitive Protected Health Information (PHI) on behalf of patients across multiple participating healthcare facilities. Under the **Ghana Data Protection Act, 2012 (Act 843)**, health and medical data constitutes a *special category of sensitive personal data* requiring heightened safeguards and explicit statutory justification.

### Cross-Hospital Access Under Act 843 §28(b) & §29

A critical legal and clinical requirement of any national or inter-hospital health information exchange is that life-saving cross-facility care cannot be paralyzed by the absence of pre-configured elective consent tokens. In mEd, cross-hospital clinical data access is legally anchored in two explicit provisions of Act 843:

1. **Section 28(b) ("Vital Interests")**:
   > Authorizes processing of sensitive personal data where *“the processing is necessary in order to protect the vital interests of the data subject or of another person in a case where consent cannot be given by or on behalf of the data subject...”*  
   This provides the statutory foundation for **Emergency Break-the-Glass (`BreakGlassAccess`)** workflows and acute referral admissions where an unconscious, incapacitated, or emergency trauma patient cannot grant affirmative electronic consent.

2. **Section 29 ("Medical Purposes by Health Professionals")**:
   > Authorizes the processing of health data where *“the processing is necessary for the purposes of preventive medicine, medical diagnosis, the provision of care or treatment or the management of healthcare services, and where the data is processed by or under the responsibility of a health professional subject to the duty of professional secrecy under law or code established by a competent body.”*  
   This establishes the statutory justification for **Treatment Relationship (`TreatmentRelationship`)** access. Access is restricted strictly to licensed clinical users (`DOCTOR`, `NURSE`, `LAB_TECH`) actively treating the patient, verified through institution-level authentication and role-based access control.

### Role of `PatientConsent`: Advisory Directives vs. Blocking Gates

Under this legal framework:
- **Acute & Inter-Hospital Care**: Cross-facility access is justified under **Act 843 §28(b) & §29**, backed by mandatory, immutable cryptographic audit logging (`is_cross_hospital=True`).
- **`PatientConsent` (`access/models.py`)**: Functions in the current prototype as an **advisory patient preference directive**. It captures patient-expressed sharing preferences without introducing clinical risk by arbitrarily withholding emergency medical history during life-threatening acute episodes.
- **Future Production Governance**: Future iterations will implement granular exclusion directives (allowing competent patients to flag specific sensitive outpatient records, such as psychiatric or reproductive health encounters, for non-emergency elective referrals) while preserving vital-interest emergency overrides under §28(b).

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
| **Right to restrict processing** | Partial | Advisory preference via `PatientConsent`. In acute referrals and emergencies, cross-hospital exchange proceeds under Act 843 §28(b) ("Vital Interests") and §29 ("Medical Purposes"), balancing data protection rights with clinical life safety. Dynamic granular elective enforcement is planned future work (ADR-009). |
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
