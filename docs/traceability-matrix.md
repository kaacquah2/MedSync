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
| FR-08 | EMPI duplicate detection at registration | `patients/empi.py::match_patient()`; wired into `patients/views.py::patient_create` | `tests/test_phase_b.py::TestEMPIDuplicateDetection` (implemented & passing) |
| FR-09 | Structured coding: ICD-10, LOINC, RxNorm, SNOMED | `records/models.py::Diagnosis.icd_code + snomed_code`; `LabResult.loinc_code`; `Prescription.rxnorm_code` | Migration `0002_diagnosis_snomed_code_…`; form fields |
| FR-10 | FHIR R4 read endpoints | `fhir/views.py::patient_resource`, `patient_everything_endpoint`; `fhir/mappers.py` | `tests/test_fhir.py` (17 tests implemented & passing) |
| FR-11 | Tamper-evident audit log hash chain | `audit/models.py::compute_row_hash`; `audit/utils.py::log_action` (chain computation); `audit/management/commands/verify_audit_chain.py` | `tests/test_audit.py::TestAuditHashChain` |
| FR-12 | Auto-create TreatmentRelationship on encounter creation | `access/permissions.py::ensure_treatment_relationship`; called from `records/views.py::encounter_create` | `tests/test_access.py::TestAutoTreatmentRelationship` |

---

## NFR Traceability

| NFR | Target | Implementation | Test / Verification |
|---|---|---|---|
| Response time p95 < 500 ms | Patient record fetch | Blind-index search (O(log n)); `select_related` / `prefetch_related` on queries; Neon connection pooling in prod | Verified locally via `scripts/benchmark_concurrency.py` (p95 ~8.8 ms at c=1 to 107.4 ms at c=50 on read path). Formal multi-hospital WAN load testing is future work. |
| 99.5% availability | Monthly uptime | Docker `restart: on-failure`; healthcheck at `/healthz/`; Neon serverless HA | `/healthz/` endpoint verified in `emr/urls.py` |
| 50 concurrent sessions | Stateless app + server-side sessions | Gunicorn multi-worker (env var); session in Postgres (or Redis in prod) | Architectural trade-off: Audit log writes are intentionally synchronous and serialized via PostgreSQL transactional advisory lock (`pg_advisory_xact_lock(0x6D456400)`, see ADR-005) to guarantee SHA-256 hash-chain linearity without race conditions. Benchmarked via `scripts/benchmark_concurrency.py`; formal high-concurrency write stress testing is planned future work. |
| RTO < 4 h, RPO < 1 h | DR | Documented backup/restore procedure (`docs/architecture.md`); Neon branching for point-in-time restore | Manual restore drill (documented, not automated) |
| Account lockout (5 failures) | Credential stuffing mitigation | `django-axes` — `AXES_FAILURE_LIMIT=5`, 1-hour cooldown | `tests/test_auth.py::TestAxesLockout` |
| Session timeout (15 min idle) | Unattended workstations | `SESSION_COOKIE_AGE=900`, `SESSION_SAVE_EVERY_REQUEST=True` (hardened per HIPAA §164.312(a)(2)(iii)) | Verified in `emr/settings.py` & `tests/test_auth.py` |
