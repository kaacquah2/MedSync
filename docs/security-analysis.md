# Security Analysis — mEd Secure Centralised EMR System

## Overview

This document presents a structured security analysis of the mEd system using the
**STRIDE** threat-modelling framework (Spoofing, Tampering, Repudiation,
Information Disclosure, Denial of Service, Elevation of Privilege). For each
category, threats are identified, and the mitigations implemented in the prototype
are described. Residual risks and assumptions are noted at the end.

---

## 1. STRIDE Threat Model

### 1.1 Spoofing (Identity Threats)

Spoofing attacks attempt to impersonate a legitimate user or system.

| Threat | Attack Vector | Mitigation Implemented | Residual Risk |
|--------|--------------|----------------------|---------------|
| **Credential theft** | Attacker obtains a valid username/password (phishing, shoulder surfing) | Session authentication; sessions expire after 1 hour; cookies are HttpOnly+Secure (production) | High in shared-workstation environments — partially mitigated by short session timeout |
| **Brute-force login** | Automated password guessing | `django-axes`: lockout after 5 failed attempts; 1-hour cooldown; lockout logged in `AuditLog` | Low after implementation |
| **Weak password** | Short or guessable passwords | Password validators enforce ≥10 chars, no common passwords, no entirely numeric | Moderate — users may use minimum-compliant weak passwords |
| **Session hijacking** | Network interception of session cookie | TLS/HTTPS enforced (`sslmode=require` for Neon; `SECURE_SSL_REDIRECT` in production); `SESSION_COOKIE_SECURE=True` | Low in production; HTTPS must be enforced at the load-balancer level |
| **MFA bypass** | Attacker has password but not authenticator | TOTP MFA enforced for all roles accessing PHI (DOCTOR, NURSE, LAB_TECH, SYSTEM_ADMIN, HOSPITAL_ADMIN) when `MFA_ENFORCED=True`; TOTP is time-limited (30s window) | Low when MFA is enforced; demo mode has MFA off by design |

### 1.2 Tampering (Integrity Threats)

Tampering attacks attempt to modify data in transit or at rest.

| Threat | Attack Vector | Mitigation Implemented | Residual Risk |
|--------|--------------|----------------------|---------------|
| **In-transit data modification** | MITM attack altering API calls or DB queries | TLS enforced end-to-end (browser → Django → Neon via `sslmode=require`) | Low — mitigated by standard TLS |
| **Database direct edit** | Attacker with DB access modifies patient records | Field-level Fernet encryption: plaintext is never written to the DB; an attacker without the key sees only ciphertext | Moderate — a DB admin with the `FIELD_ENCRYPTION_KEY` could decrypt; mitigated in production by HSM/secret management |
| **Audit log tampering** | Admin attempts to delete or modify audit entries | `AuditLog.save()` raises `ValueError` if `pk` exists; `delete()` raises; Django admin disables edit/delete buttons | Low — append-only enforced at application layer; a `SYSTEM_ADMIN` with direct DB access could bypass this |
| **Blind-index collision** | Adversary engineers two inputs with the same HMAC | HMAC-SHA256 with secret key: pre-image and collision attacks require knowledge of the key; collision probability is negligible (256-bit output) | Very low |

### 1.3 Repudiation (Non-Repudiation Failures)

Repudiation threats arise when an actor can deny performing an action.

| Threat | Attack Vector | Mitigation Implemented | Residual Risk |
|--------|--------------|----------------------|---------------|
| **Deny viewing a patient record** | "I never accessed that patient" | Every `VIEW_PATIENT`, `VIEW_ENCOUNTER` logged with actor, role, hospital, timestamp, IP, cross-hospital flag | Low — audit logs are append-only; actor identity tied to authenticated session |
| **Deny cross-hospital access** | Clinician denies accessing another hospital's records | `is_cross_hospital=True` flag written to `AuditLog` with actor and patient NHID | Low |
| **Shared accounts** | Multiple users sharing one login to dilute accountability | RBAC requires individual accounts; unique `username` enforced | Moderate in practice — policy enforcement required |
| **No MFA proof of identity** | Password shared between users | MFA (TOTP) adds a second factor tied to a physical device | Low when MFA is enforced |

### 1.4 Information Disclosure (Confidentiality Threats)

| Threat | Attack Vector | Mitigation Implemented | Residual Risk |
|--------|--------------|----------------------|---------------|
| **PHI in database plaintext** | DB backup or SQL injection exposes patient names/diagnoses | Fernet AES-128-CBC + HMAC on all PII/PHI columns; DB backup contains only ciphertext | Low — mitigated by encryption at application layer + Neon storage-level encryption |
| **PHI in logs** | Application logs capture sensitive field values | Custom encrypted fields (`EncryptedCharField`) never log decrypted values; Django logging configured at WARNING level | Moderate — DEBUG logs could reveal decrypted values if DEBUG=True in production |
| **Blind-index exposure (exact match)** | HMAC values in DB reveal whether two patients share a name | HMAC is keyed with `BLIND_INDEX_KEY`; without the key, the HMAC reveals nothing about the plaintext | Low |
| **Trigram token de-anonymization (partial search)** | Small keyspace (~17.5k) of 3-character tokens in `PatientSearchToken` allows precomputed rainbow tables or frequency analysis to reconstruct names | Independent `BLIND_INDEX_KEY` enforced in production (`DEBUG=False`); partial search scoped to home hospital for non-admins; all searches audit-logged (`SEARCH_PATIENT`) | Moderate — inherent trade-off of deterministic substring indexing |
| **Excessive data exposure in API** | Views return more data than needed | Views use Django's ORM with explicit field selection; templates render only what is needed | Moderate — no formal output encoding review performed |
| **Encryption key exposure** | `FIELD_ENCRYPTION_KEY` in source code or logs | Key stored in environment variable; `.env` file is `.gitignore`d; Docker environment variable | Moderate — key management relies on environment security; production should use a KMS |

### 1.5 Denial of Service (Availability Threats)

| Threat | Attack Vector | Mitigation Implemented | Residual Risk |
|--------|--------------|----------------------|---------------|
| **Login brute force (DoS)** | Lock out legitimate users by triggering the 5-attempt lockout | Lockout is per IP + per username (configurable); SYSTEM_ADMIN can manually reset via Django admin | Moderate — can lock out legitimate users if an attacker knows their username |
| **Large file upload** | Malicious file upload exhausting disk | No file upload functionality in v1; only text and structured data | Low |
| **DB connection exhaustion** | Neon connection limit exceeded | Neon has connection pooling; Gunicorn has a bounded worker count (2 workers in Docker) | Moderate at scale — pgBouncer recommended for production |

### 1.6 Elevation of Privilege (Authorisation Threats)

| Threat | Attack Vector | Mitigation Implemented | Residual Risk |
|--------|--------------|----------------------|---------------|
| **Role escalation** | Low-privilege user accesses high-privilege view | RBAC enforced on every view via `@role_required` decorator and `RoleRequiredMixin`; every violation raises 403 and is logged | Low |
| **IDOR (Insecure Direct Object Reference)** | Accessing another user's patient by guessing PK | Patient lookup uses `universal_id` (opaque, hard to guess); FKs use auto-incrementing IDs but access is gated by authentication | Moderate — NHIDs are predictable patterns; obscurity is not a security control |
| **CSRF** | Cross-site request forgery forcing a user to take actions | Django's built-in CSRF middleware enabled on all POST forms; `CSRF_COOKIE_SECURE=True` in production | Low |
| **SQL injection** | Malicious input in search/query fields | All DB access via Django ORM parameterised queries; no raw SQL in user-facing code | Low |
| **Session fixation** | Attacker fixes session ID before login | Django rotates session ID on login | Low |

---

## 2. Security Controls Implemented

| Control | Implementation | Standard/Reference |
|---------|---------------|-------------------|
| Authentication | Django session auth; password hashed with Argon2/PBKDF2 | OWASP ASVS V2 |
| Multi-Factor Authentication | TOTP via `django-otp`; enforced for all PHI-accessing roles | NIST SP 800-63B Level 2 |
| Role-Based Access Control | 6-role model; enforced per view; 403 audited | OWASP ASVS V4 |
| Encryption at rest (field-level) | Fernet (AES-128-CBC + HMAC-SHA256) on all PII/PHI | HIPAA §164.312(a)(2)(iv); GDPR Art. 32 |
| Encryption at rest (storage) | Neon (PostgreSQL) encrypts storage by default | Additional layer |
| Encryption in transit | TLS via `sslmode=require` (DB); HTTPS in production | OWASP TLS Cheat Sheet |
| Blind-index search | HMAC-SHA256 keyed hashes for encrypted-column lookups | Dan Bernstein, "Leakage-Resilient Encryption" patterns |
| Audit logging | Append-only `AuditLog`; every PHI access, 403, login/logout | HIPAA §164.312(b); ISO 27001 A.12.4 |
| Cross-hospital access flagging | `is_cross_hospital` field in every audit record | Bespoke — reflects clinical workflow separation |
| Brute-force protection | `django-axes`; 5-attempt lockout; lockout audited | OWASP Credential Stuffing Prevention |
| Session security | 1-hour idle timeout; `SESSION_COOKIE_SECURE`; `SESSION_COOKIE_HTTPONLY` | OWASP Session Management Cheat Sheet |
| CSRF protection | Django CSRF middleware; token on every form | OWASP CSRF Prevention |
| Security headers (production) | HSTS; XSS filter; X-Frame-Options DENY; Content-Type nosniff | OWASP Secure Headers |
| Password policy | ≥10 chars; no common/attribute-similar passwords | NIST SP 800-63B §5.1.1 |
| Health endpoint | `/healthz/` — DB connectivity probe for orchestration | Kubernetes/Docker best practice |

---

## 3. Residual Risks and Assumptions

| Risk | Severity | Notes |
|------|----------|-------|
| Encryption key management | **HIGH** | In production, `FIELD_ENCRYPTION_KEY` and `BLIND_INDEX_KEY` must be stored in a secret manager (AWS Secrets Manager, HashiCorp Vault, GCP Secret Manager) — not an `.env` file. Loss of these keys = permanent loss of all encrypted data. |
| MFA disabled in demo mode | **MEDIUM** | `MFA_ENFORCED=False` when `DEBUG=True` is intentional for demo usability, but must be set to `True` before any real-data deployment. |
| Partial-name search trigram entropy | **MODERATE** | Substring lookups use HMAC-SHA256 trigrams in `PatientSearchToken` (migrations 0005/0006), eliminating O(N) memory scans. However, the small keyspace (~17.5k Latin trigrams) is vulnerable to offline dictionary attack if `BLIND_INDEX_KEY` is compromised. Mitigated by key separation, hospital-scoped searches, and audit logging (`SEARCH_PATIENT`). See `known_limitations.md` §1. |
| No row-level access control | **MEDIUM** | Any authenticated clinical role can view any patient's record. For strict data minimisation (GDPR/HIPAA), patient consent management (scoped access per hospital) would be required. |
| Shared workstation risk | **MEDIUM** | 1-hour session timeout partially mitigates this, but physical access to an unlocked workstation still allows unauthorized access. Screen-lock policies and physical controls are required. |
| No audit log integrity proof | **MEDIUM** | Audit entries are append-only at the application layer. A SYSTEM_ADMIN with direct DB access can bypass this. For production, write-ahead logs or an immutable log store (e.g. Neon's branching, or a WORM-compliant store) should be used. |
| No FHIR/HL7 interoperability | **LOW** | The system uses a bespoke data model. Integration with national health information exchange would require an HL7 FHIR R4 API layer. |
| Break-glass MFA re-verification skippable | **MEDIUM** | Break-glass MFA re-verification is conditional, not unconditional. In `api/views/patients.py::BreakGlassView`, TOTP re-verification is only required if the user has an existing confirmed TOTP device. If a clinician reaches a session without having enrolled a TOTP device, the break-glass view bypasses re-verification and issues the grant with `mfa_reverified=False`. This design intentionally avoids locking out clinicians during life-critical emergencies, but means clinicians who have not enrolled TOTP avoid second-factor re-verification entirely. Mitigated by append-only audit logging of `mfa_reverified` status and mandatory administrative break-glass reviews. |

---

## 4. Compliance Notes

| Regulation | Applicability | Status |
|------------|--------------|--------|
| **GDPR (EU)** | If any EU patients or staff are involved | Partial — encryption, access control, and audit logging are implemented; DPA registration, DPO appointment, Data Processing Agreements, and right-to-erasure are out of scope for v1 |
| **HIPAA (US)** | If US patients; or cloud infrastructure in US jurisdiction | Partial — technical safeguards (encryption, audit, access control) implemented; administrative and physical safeguards (BAAs, training, physical security) out of scope |
| **Ghana Data Protection Act 2012** | Primary jurisdiction | Partial — data minimisation (encryption), security measures, audit logging implemented; formal DPA compliance not audited |
| **ISO 27001** | Information security management | Controls A.9 (access control), A.10 (cryptography), A.12.4 (logging), A.14 (secure development) addressed; formal ISMS and certification process not in scope |

---

## 5. Post-Sprint Security Additions

The following controls were added in the current build sprint and update the analysis above:

| Control | Implementation | Threat mitigated |
|---|---|---|
| **Object-level inter-hospital access gate** | `access/permissions.py::can_access_patient()` — denies cross-hospital access without TreatmentRelationship, BreakGlassAccess, or admin privilege | IDOR (cross-hospital); §3 §1.6 |
| **Break-the-glass** | `access/models.py::BreakGlassAccess`; `api/views/patients.py::BreakGlassView` — reason-required, conditional re-MFA (only enforced if user has enrolled TOTP device; not unconditional), 1-hour TTL, audited with `mfa_reverified` status | Balances clinical access with auditability; see ADR-006 |
| **Treatment relationship auto-creation** | `access/permissions.py::ensure_treatment_relationship` — called on encounter creation | Ensures ongoing care is not blocked by the gate |
| **Audit hash chain (tamper evidence)** | `audit/models.py::compute_row_hash`; `audit/utils.py::log_action`; SHA-256 chain per row | Tampering with audit log is detectable (§1.2 residual risk resolved) |
| **Postgres immutability trigger** | `audit/migrations/0003_auditlog_immutability_trigger.py` | DB-level enforcement of audit immutability |
| **MFA backup recovery codes** | `accounts/models.py::RecoveryCode`; generated at enrolment; SHA-256 hashed at rest; single-use | Prevents account lockout when TOTP device is lost |
| **Trusted-device window** | `accounts/mfa_middleware.py::MFAEnforcementMiddleware` — signed cookie (8 h default) | Reduces MFA friction for shift-length workflows without removing the control |
| **Password minimum length 12 chars** | `settings.AUTH_PASSWORD_VALIDATORS` | NIST SP 800-63B §5.1.1 (upgrade from 10 chars) |
| **FHIR R4 access gate** | `fhir/views.py` — FHIR endpoints pass through `can_access_patient()` | Same gate as UI; FHIR is not a bypass path |
| **EMPI duplicate detection** | `patients/empi.py::match_patient()` — blocks on exact national-ID match | Prevents care-fragmenting duplicate records |
| **PostgreSQL Row-Level Security (defense-in-depth)** | `audit/migrations/0010_auditlog_rls.py`, `records/migrations/0007_encounter_rls.py`; GUCs set by `core.middleware.RLSContextMiddleware`; bypass via `core.rls.rls_bypass()` for management commands | Database-level protection against app-layer query bugs and most SQL injection — see §5a |

---

## 5a. Row-Level Security (Defense-in-Depth)

PostgreSQL Row-Level Security (RLS) is enabled on two tables:

| Table | Policies | Effect |
|-------|----------|--------|
| `audit_auditlog` | `audit_select` (admin or bypass only), `audit_insert` (always) | Only super_admin / hospital_admin can read the audit trail; clinicians see nothing via raw SQL |
| `records_encounter` | `encounter_select` / `encounter_update` (mirrors `can_access_patient()`), `encounter_insert` (always) | A stray `SELECT * FROM records_encounter` returns only the rows the current user is allowed to see at the application layer |

### How it works

`FORCE ROW LEVEL SECURITY` is used so that even the table owner (the Django role that ran the migrations) is subject to the policies.  Policies consult three PostgreSQL custom GUCs set per HTTP request by `core.middleware.RLSContextMiddleware`:

```
app.user_id       — authenticated user PK ('' for anonymous)
app.hospital_id   — user's home hospital PK ('' for super_admin or no hospital)
app.is_admin      — 'on' for super_admin / hospital_admin, else 'off'
```

The middleware sets these at the session level (`set_config(name, value, false)`) so they persist across the per-statement auto-commit transactions Django uses under autocommit mode, then resets them to safe defaults in a `try/finally` block so pooled connections are never reused with stale identity.

Management commands and admin shell operations use `core.rls.rls_bypass()` (sets `app.bypass_rls = 'on'`).

### Access model for encounters (mirrors `can_access_patient()`)

```
bypass_rls = 'on'  →  allowed (management commands)
is_admin   = 'on'  →  allowed (super_admin / hospital_admin)
created_at_hospital_id = app.hospital_id  →  allowed (same-hospital clinician)
active TreatmentRelationship(clinician_id, patient_id)  →  allowed
unexpired BreakGlassAccess(actor_id, patient_id)        →  allowed
otherwise  →  denied (zero rows returned)
```

### Honest limitations

This design uses a **single database role** for all application queries.  RLS therefore protects against:
- Application-layer bugs (a forgotten `.filter()` in a view returning all encounters)
- SQL injection that does not also execute `SET app.is_admin = 'on'`

It does **not** protect against a fully compromised database connection or a compromised Django process, because the attacker could set their own GUCs.  This is an inherent limitation of single-role designs; the primary access controls remain the application-layer gates (`can_access_patient()`, DRF authentication, Fernet encryption).

Neon's marketed "RLS / Neon Authorize" (JWT + `authenticated`/`anon` roles) is designed for browser-direct Postgres access and does **not** apply here — only the Django backend connects to Neon.

### Rollback

```bash
python manage.py migrate audit 0009      # removes audit_auditlog RLS
python manage.py migrate records 0006    # removes records_encounter RLS
# Remove "core.middleware.RLSContextMiddleware" from MIDDLEWARE in settings.py
```

---

## 6. Least-Privilege DB Role (Production Recommendation)

The application DB role should have the following grants:
- `SELECT, INSERT` on `audit_auditlog` — **no UPDATE or DELETE**.
- `SELECT, INSERT, UPDATE, DELETE` on all other application tables.
- The Postgres immutability trigger (ADR-005) enforces this at the DB level regardless of the role's actual grants.

Document this in the database provisioning runbook.

---

## 7. What a Real Deployment Would Add

- **HSM-backed encryption keys** (AWS CloudHSM, GCP Cloud KMS) instead of environment-variable `FIELD_ENCRYPTION_KEY`.
- **Formal penetration test** (OWASP DAST / third-party pen-tester) before going live.
- **Badge-tap SSO** (Imprivata or SAML 2.0) for clinical workstations — TOTP becomes the remote / admin channel.
- **WebAuthn / passkeys** for SYSTEM_ADMIN and HOSPITAL_ADMIN (phishing-resistant second factor).
- **HIBP breach-check** on password set (`k-anonymity` API query to `haveibeenpwned.com`).
- **PgBouncer + read replica** for DB HA and connection pooling.
- **Celery + Redis** for async audit writes, alert notifications, and FHIR bundle generation.
