# Traceability Matrix

Links every functional requirement to the design element that implements it and the test that verifies it.

| Req ID | Requirement | Design Element | Test |
|---|---|---|---|
| FR-01 | Central patient registry with universal NHID | `patients/models.py::Patient.universal_id` (NHID-XXXXXXXX, unique, db_index) | `tests/test_patients.py::TestNHID` |
| FR-02 | Field-level encryption of PII/PHI | `core/fields.py::EncryptedCharField` / `EncryptedTextField` (Fernet); `FIELD_ENCRYPTION_KEY` env var | `tests/test_encryption.py` |
| FR-03 | Six clinical roles; deny-by-default | `accounts/models.py::User.Role`; `core/mixins.py::RoleRequiredMixin`; `@role_required` decorator | `tests/test_rbac.py` (all negative authz tests) |
| FR-04 | Patient access gate (treatment relationship / break-glass / same-hospital / admin) | `access/permissions.py::can_access_patient()`; `patients/views.py::patient_detail`; `records/views.py` | `tests/test_access.py::TestCanAccessPatient`, `TestPatientDetailGate` |
| FR-05 | Break-the-glass (reason + conditional re-MFA + time-boxed + audited) | `api/views/patients.py::BreakGlassView`; `access/models.py::BreakGlassAccess` | `tests/test_access.py::TestBreakGlassRequest` |
| FR-06 | Immutable PHI audit log on every read/write | `audit/models.py::AuditLog` (save/delete guards); `audit/utils.py::log_action`; called from all views | `tests/test_audit.py::TestAuditLogImmutability`, `TestLogAction`, `TestAccessDeniedAudit` |
| FR-07 | MFA enforcement (TOTP) for clinical/admin roles | `accounts/mfa_middleware.py::MFAEnforcementMiddleware`; `accounts/views.py::mfa_setup/verify`; `settings.MFA_ENFORCED` | `tests/test_auth.py` (MFA enrolment / verify flows) |
| FR-08 | EMPI duplicate detection at registration | `patients/empi.py::match_patient()`; wired into `patients/views.py::patient_create` | `tests/test_patients.py::TestEMPIDuplicateDetection` *(to add)* |
| FR-09 | Structured coding: ICD-10, LOINC, RxNorm, SNOMED | `records/models.py::Diagnosis.icd_code + snomed_code`; `LabResult.loinc_code`; `Prescription.rxnorm_code` | Migration `0002_diagnosis_snomed_code_…`; form fields |
| FR-10 | FHIR R4 read endpoints | `fhir/views.py::patient_resource`, `patient_everything_endpoint`; `fhir/mappers.py` | `tests/test_fhir.py` *(to add)* |
| FR-11 | Tamper-evident audit log hash chain | `audit/models.py::compute_row_hash`; `audit/utils.py::log_action` (chain computation); `audit/management/commands/verify_audit_chain.py` | `tests/test_audit.py::TestAuditHashChain` |
| FR-12 | Auto-create TreatmentRelationship on encounter creation | `access/permissions.py::ensure_treatment_relationship`; called from `records/views.py::encounter_create` | `tests/test_access.py::TestAutoTreatmentRelationship` |

---

## NFR Traceability

| NFR | Target | Implementation | Test / Verification |
|---|---|---|---|
| Response time p95 < 500 ms | Patient record fetch | Blind-index search (O(log n)); `select_related` / `prefetch_related` on queries; Neon connection pooling in prod | Load test (k6/Locust — not yet wired; see ADR-06) |
| 99.5% availability | Monthly uptime | Docker `restart: on-failure`; healthcheck at `/healthz/`; Neon serverless HA | `/healthz/` endpoint verified in `emr/urls.py` |
| 50 concurrent sessions | Stateless app + server-side sessions | Gunicorn multi-worker (env var); session in Postgres (or Redis in prod) | Load test — documented in ADR-06 |
| RTO < 4 h, RPO < 1 h | DR | Documented backup/restore procedure (`docs/architecture.md`); Neon branching for point-in-time restore | Manual restore drill (documented, not automated) |
| Account lockout (5 failures) | Credential stuffing mitigation | `django-axes` — `AXES_FAILURE_LIMIT=5`, 1-hour cooldown | `tests/test_auth.py::TestAxesLockout` |
| Session timeout (1 h idle) | Unattended workstations | `SESSION_COOKIE_AGE=3600`, `SESSION_SAVE_EVERY_REQUEST=True` | Verified in settings |
