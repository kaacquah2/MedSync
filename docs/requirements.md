# Requirements Specification — Secure Centralized Inter-Hospital EMR

## 1. Actor / Stakeholder Catalogue

| Actor | Type | Goals / Responsibilities |
|---|---|---|
| **Patient** | Human | Receive care; have their records available at any participating hospital; control who accesses their data. |
| **Doctor** | Clinical human | Read/write complete patient records; prescribe medications; request lab tests; access records at other hospitals for referred patients. |
| **Nurse** | Clinical human | View and update clinical records; document encounters; administer medication per prescription. |
| **Lab Technician** | Clinical human | Record lab results against an encounter; view relevant patient demographics. |
| **Receptionist** | Administrative human | Register patients; search the registry; schedule appointments; no access to clinical notes. |
| **Hospital Admin** | Administrative human | Manage staff accounts within their hospital; view hospital-level statistics. |
| **System Admin** | Technical human | Full system access; manage hospitals; view audit trail; resolve identity conflicts. |
| **Referring Hospital** | Institutional actor | Source of a referral; expects receiving hospital to have access to relevant history. |
| **External Lab** | Institutional actor | Delivers structured lab results (future: HL7 v2 ORU feed). |
| **Central EMR System** | Software actor | Central node; enforces access control; stores all records; exposes API. |

---

## 2. User Stories / Use Cases per Role

### Patient
- As a patient, I want my medical history to be accessible at any participating hospital so I don't have to re-explain my conditions in an emergency.
- As a patient, I want to know which hospitals have accessed my records.
- As a patient, I want to be able to see which hospitals have consent to share my data.

### Doctor
- As a doctor, I can view and update the full record of any patient currently under my care.
- As a doctor referring a patient to another hospital, I want the receiving clinician to have access to the relevant history.
- As a doctor at a receiving hospital, I can access a referred patient's records — gated by a treatment relationship established at referral.
- As a doctor, if I encounter an unconscious/incapacitated patient I have no prior relationship with, I can break the glass with a clinical justification to access their emergency record.
- As a doctor, I can create diagnoses with structured ICD-10 codes for interoperability.

### Nurse
- As a nurse, I can document encounters and update clinical notes for patients under my care.
- As a nurse, I cannot prescribe medications (role-restricted).

### Lab Technician
- As a lab tech, I can record lab results with LOINC codes against an existing encounter.

### Receptionist
- As a receptionist, I can register a new patient; the system warns me if a patient with the same national ID or name+DOB already exists (EMPI duplicate check).
- As a receptionist, I can search the central patient registry by NHID, name, or national ID.

### Hospital Admin
- As a hospital admin, I can create, edit, and deactivate staff accounts within my hospital.
- As a hospital admin, I can view break-glass access events for my hospital for compliance review.

### System Admin
- As a system admin, I can view the full audit trail across all hospitals.
- As a system admin, I can manage hospital registrations and staff roles.
- As a system admin, I can verify the audit log hash chain has not been tampered with.

---

## 3. Core Functional Requirements

| ID | Requirement | Priority |
|---|---|---|
| FR-01 | The system shall maintain a central patient registry identified by a unique National Health ID (NHID). | Must |
| FR-02 | All PII/PHI shall be encrypted at rest at the field level (Fernet AES-128-CBC). | Must |
| FR-03 | The system shall support six clinical roles with deny-by-default access. | Must |
| FR-04 | A clinician may access a patient's record only with an active TreatmentRelationship, a BreakGlassAccess, same-hospital registration, or admin privilege. | Must |
| FR-05 | Break-the-glass access shall require a non-blank clinical reason, optional re-MFA, and shall be time-boxed to 1 hour and audited. | Must |
| FR-06 | Every read or write of PHI shall produce one immutable AuditLog entry. | Must |
| FR-07 | MFA (TOTP) shall be enforced for all clinical and admin roles in production. | Must |
| FR-08 | The system shall detect probable duplicate patients at registration using EMPI matching on national ID and name+DOB. | Must |
| FR-09 | Diagnoses shall be coded in ICD-10; lab results in LOINC; prescriptions may carry RxNorm codes. | Should |
| FR-10 | The system shall expose FHIR R4 read endpoints for the Patient resource and $everything bundle. | Should |
| FR-11 | The audit log shall be tamper-evident via a SHA-256 hash chain. | Should |
| FR-12 | Creating an encounter shall automatically open a TreatmentRelationship for future access. | Must |

---

## 4. Non-Functional Requirements (Quantified)

| Attribute | Target | Rationale |
|---|---|---|
| **Response time** | p95 single-patient record fetch < 500 ms (excluding first DB cold-start on Neon serverless) | Clinical workflows must not be delayed. |
| **Availability** | 99.5% monthly uptime (single-instance prototype target) | Production HA target: 99.9% with primary/read-replica failover (see ADR-01). |
| **Concurrency** | Support 50 concurrent authenticated clinician sessions without p95 degradation | Sized for a 3-hospital pilot (approx. 50 active clinical users). |
| **RTO** | Recovery Time Objective: < 4 hours for full service restore from backup | From documented restore procedure. |
| **RPO** | Recovery Point Objective: < 1 hour data loss (production target via managed PostgreSQL WAL archiving; prototype provides manual backup scripts in `scripts/backup.sh` and `python manage.py export_backup`) | Neon/cloud WAL point-in-time recovery in production; manual DB + media export provided for prototype deployment and testing. |
| **Audit retention** | 30-day hot-database retention with local WORM JSON archival (`prune_audit_logs`); 10-year statutory retention planned via cloud WORM storage | Balances local storage constraints with hash-chain continuity via archive anchors (ADR-005); long-term statutory compliance requires external cold storage (see `known_limitations.md §3`). |
| **Encryption** | AES-128-CBC (Fernet) with HMAC-SHA256 for field-level PII/PHI; TLS 1.3 in transit; AES-256 for disk/backup encryption at rest | Industry standard for PHI. |
| **Lockout** | Account locked after 5 failed login attempts; 1-hour cooldown | Mitigates credential-stuffing attacks. |
| **Session timeout** | 1-hour idle session expiry; auto-lock on inactivity | Clinical workstations are frequently unattended. |

---

## 5. Domain Glossary

| Term | Definition |
|---|---|
| **NHID** | National Health ID — the universal patient identifier in the mEd system (format: `NHID-XXXXXXXX`). |
| **Encounter** | A discrete clinical visit or contact between a patient and a facility (OPD, IPD, Emergency, etc.). |
| **Episode** | A collection of related encounters for a single condition or illness. Not currently modelled separately; represented by the Encounter chain. |
| **Referral** | The inter-hospital process by which one clinician transfers a patient to another facility. Triggers a TreatmentRelationship at the receiving hospital. |
| **TreatmentRelationship** | An active, time-bounded link between a clinician and patient granting cross-hospital record access. |
| **BreakGlassAccess** | An emergency override allowing a clinician to access a record without a TreatmentRelationship. Requires reason; time-boxed; audited. |
| **Consent** | Patient's expressed preference for which hospitals may access their records. Stored in PatientConsent; currently advisory, not a hard enforcement gate. |
| **PHI** | Protected Health Information — any field that identifies or could identify a patient when combined with medical data. |
| **EMPI** | Enterprise Master Patient Index — the system/process that resolves multiple records to the same unique person. |
| **Tenant** | A participating hospital in the multi-hospital system. Staff belong to a tenant; patients are shared/central. |
| **Blind index** | An HMAC-SHA256 of a normalised plaintext value, stored alongside the encrypted field to enable exact-match searches without decrypting all rows. |

---

## 6. Data Dictionary (PHI Classification)

| Model | Field | Type | PHI? | Encrypted | Notes |
|---|---|---|---|---|---|
| Patient | universal_id | CharField | No | No | System-generated NHID; safe to store plaintext. |
| Patient | first_name | EncryptedChar | **Yes** | Fernet | Ciphertext in DB; blind-indexed via name_hash. |
| Patient | last_name | EncryptedChar | **Yes** | Fernet | Ciphertext in DB; blind-indexed via name_hash. |
| Patient | date_of_birth | EncryptedChar | **Yes** | Fernet | Stored as YYYY-MM-DD string. |
| Patient | national_id | EncryptedChar | **Yes** | Fernet | Ghana Card / passport; blind-indexed via national_id_hash. |
| Patient | phone | EncryptedChar | **Yes** | Fernet | |
| Patient | email | EncryptedChar | **Yes** | Fernet | |
| Patient | address | EncryptedText | **Yes** | Fernet | |
| Patient | sex | CharField | Indirect | No | Not re-identifying alone; stored plaintext. |
| Patient | blood_group | CharField | Indirect | No | |
| Encounter | chief_complaint | EncryptedText | **Yes** | Fernet | Clinical narrative. |
| Encounter | notes | EncryptedText | **Yes** | Fernet | |
| Diagnosis | description | EncryptedText | **Yes** | Fernet | icd_code/snomed_code stored plaintext (coded, not narrative). |
| Prescription | drug_name | EncryptedChar | **Yes** | Fernet | |
| Prescription | dosage | EncryptedChar | **Yes** | Fernet | |
| Prescription | frequency | EncryptedChar | **Yes** | Fernet | |
| Prescription | instructions | EncryptedText | **Yes** | Fernet | |
| LabResult | test_name | EncryptedChar | **Yes** | Fernet | |
| LabResult | result_value | EncryptedText | **Yes** | Fernet | |
| AuditLog | — | — | Metadata | No | Stores actor/action/target, not PHI values. |
| User | — | — | PII | No | Staff PII; not patient PHI. |
