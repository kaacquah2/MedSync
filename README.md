# mEd — Secure Centralised Electronic Medical Records System

> Academic prototype demonstrating the design and implementation of a secure, centralised Electronic Medical Record (EMR) system for inter-hospital patient record access with field-level encryption, tamper-evident audit logging, grounded AI decision support, and FHIR R4 interoperability.

---

![mEd Stack](https://img.shields.io/badge/Backend-Django%204.2-092E20?style=for-the-badge&logo=django)
![Frontend Stack](https://img.shields.io/badge/Frontend-React%2018%20%7C%20Vite%206-61DAFB?style=for-the-badge&logo=react)
![UI Framework](https://img.shields.io/badge/UI-Mantine%20v7-339AF0?style=for-the-badge&logo=mantine)
![Database](https://img.shields.io/badge/Database-PostgreSQL%20(Neon)-4169E1?style=for-the-badge&logo=postgresql)
![Encryption](https://img.shields.io/badge/Security-Fernet%20AES--128%20%2B%20HMAC-brightgreen?style=for-the-badge)
![Tests](https://img.shields.io/badge/Tests-418%20Passed-success?style=for-the-badge)

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Key System Features & Modules](#key-system-features--modules)
3. [Security Architecture & Implementation](#security-architecture--implementation)
   - [Authentication & Role-Based Access Control (RBAC)](#1-authentication--role-based-access-control-rbac)
   - [Encryption at Rest (Field-Level Encrypted PHI/PII)](#2-encryption-at-rest-field-level-encrypted-phipii)
   - [Blind Indexing for Encrypted Search](#3-blind-indexing-for-encrypted-search)
   - [Encryption in Transit & Transport Security](#4-encryption-in-transit--transport-security)
   - [Immutable Audit Logging & Tamper-Evident SHA-256 Hash Chain](#5-immutable-audit-logging--tamper-evident-sha-256-hash-chain)
   - [Inter-Hospital Access Control & Break-the-Glass Workflow](#6-inter-hospital-access-control--break-the-glass-workflow)
   - [Two-Factor Authentication (MFA / TOTP)](#7-two-factor-authentication-mfa--totp)
   - [Grounded Privacy-Aware AI Decision Support](#8-grounded-privacy-aware-ai-decision-support)
   - [FHIR R4 Interoperability](#9-fhir-r4-interoperability)
4. [Technology Stack](#technology-stack)
5. [Architecture Diagram](#architecture-diagram)
6. [Project Structure](#project-structure)
7. [Quick Start (Docker)](#quick-start-docker)
8. [Local Development](#local-development)
   - [Backend Setup (Django API)](#backend-setup-django-api)
   - [Frontend Setup (React SPA)](#frontend-setup-react-spa)
9. [Demo Credentials](#demo-credentials)
10. [Demonstrating & Verifying Security Features](#demonstrating--verifying-security-features)
11. [Running Tests](#running-tests)
12. [Academic & Architecture Documentation](#academic--architecture-documentation)
13. [Future Work](#future-work)

---

## System Overview

**mEd** addresses the clinical risk and inefficiencies caused by siloed patient data across separate healthcare facilities. Today, when a patient visits Hospital B after receiving treatment at Hospital A, clinicians often lack access to prior history — leading to duplicated diagnostics, delayed treatment, and suboptimal outcomes.

### Core Solutions Delivered:
- **Centralised Cloud Repository**: Hosted on serverless PostgreSQL (Neon) with multi-tenant logical organization.
- **Universal National Health ID (NHID)**: Unique lifetime patient identifier matching patients across disparate health systems.
- **Inter-Hospital Record Portability**: Authorized clinicians at participating hospitals can query patient histories across hospital boundaries.
- **Strict Cryptographic Security**: Field-level Fernet (AES-128-CBC + HMAC-SHA256) application-layer encryption for PII/PHI.
- **Tamper-Evident Cryptographic Audit Hash Chain**: SHA-256 chained audit entries with database-level immutability triggers.
- **Grounded AI Decision Support**: Context-aware clinical inquiry assistant powered by Gemini 2.0 Flash or local zero-egress Ollama models.
- **Dual Client Interfaces**: Server-rendered HTML templates for quick administration and a modern React 18 / Mantine v7 Single-Page Application (SPA) for high-performance clinical workflows.

---

## Key System Features & Modules

- 🏥 **Central Patient Registry & EMPI**: Deduplication matching engine with blind-indexed deterministic hash searching.
- 🩺 **Clinical Encounters & Notes**: Structured encounter logging with chief complaints, subjective/objective findings, and treatment plans.
- 📋 **Diagnoses & Terminology Coding**: ICD-10 & SNOMED CT terminology standard support.
- 💊 **Prescriptions & Pharmacy Orders**: Prescription generation with RxNorm coding.
- 🧪 **Lab Orders & Worklists**: Order creation, status tracking, worklist queues, and LOINC-coded lab results.
- 🫀 **Vitals Tracking & Trend Analysis**: Recording of blood pressure, heart rate, oxygen saturation, temperature, respiratory rate, and BMI.
- 🏬 **Infrastructure Management**: Hospital department, ward, and bed assignment tracking.
- 👨‍⚕️ **Staff Roster & Shift Handovers**: Duty shift tracking, handover note creation, and formal shift closure acknowledgments.
- 🚑 **Inter-Hospital Patient Referrals**: Outgoing and incoming referral request management across participating facilities.
- 📁 **Patient Medical Documents**: Secure attachment storage, upload, preview, and access-controlled downloading.
- 🤖 **Clinical AI Assistant**: Grounded query execution with citation enforcement and prompt-injection defenses.
- 🌐 **FHIR R4 REST API**: Read-only standard FHIR resources (`Patient`, `$everything` bundle, `Encounter`, `Condition`, `Observation`, `MedicationRequest`).

---

## Security Architecture & Implementation

### 1. Authentication & Role-Based Access Control (RBAC)

Staff accounts operate under strict Role-Based Access Control (RBAC) across six tiered roles, enforced both on backend API routes (via `RoleRequiredMixin` & `api/permissions.py`) and frontend component views (via `RequireRole`):

| Role | Permissions & Responsibilities |
|------|--------------------------------|
| `SYSTEM_ADMIN` | Full system administration; manages hospitals, views global audit logs & hash chain verification |
| `HOSPITAL_ADMIN` | Local hospital staff administration, user creation, password resets, hospital overview |
| `DOCTOR` | Full clinical access: creates encounters, diagnoses, prescriptions, lab orders, vitals, referrals, AI queries |
| `NURSE` | Clinical care support: views encounters, creates diagnoses, lab results, records vitals, shift handovers |
| `LAB_TECH` | Laboratory operations: manages lab order worklists, records lab result values (no general clinical view) |
| `RECEPTIONIST` | Administrative registration: registers new patients, updates demographics; **zero access to clinical details** |

### 2. Encryption at Rest (Field-Level Encrypted PHI/PII)

All Personally Identifiable Information (PII) and Protected Health Information (PHI) are encrypted at the **application layer** using **Fernet (AES-128-CBC + HMAC-SHA256)** via custom Django fields (`EncryptedCharField`, `EncryptedTextField`).

| Entity | Encrypted Fields |
|--------|------------------|
| **Patient** | `first_name`, `last_name`, `date_of_birth`, `national_id`, `phone`, `email`, `address` |
| **Encounter** | `chief_complaint`, `notes` |
| **Diagnosis** | `description` |
| **Prescription** | `drug_name`, `dosage`, `frequency`, `instructions` |
| **Lab Result** | `test_name`, `result_value` |

Database storage contains **only base64-encoded ciphertext** (prefixed with `gAAAAA...`), protecting data against direct database breaches or compromised DB backups.

### 3. Blind Indexing for Encrypted Search

To allow searching over encrypted fields (such as patient names and national IDs) without decrypting the entire database table in memory, mEd uses **Blind Indexing**:
```python
blind_index = hmac_sha256(key=HMAC_SECRET_KEY, msg=normalized_value.lower())
```
Search queries compute the HMAC-SHA256 digest of the query input and query the exact match on `first_name_hash`, `last_name_hash`, or `national_id_hash`.

### 4. Encryption in Transit & Transport Security

- Database connection strings mandate TLS via `sslmode=require`.
- Web traffic is served strictly over **HTTPS** in production environments.
- Security flags: `SECURE_SSL_REDIRECT=True`, `SESSION_COOKIE_SECURE=True`, `CSRF_COOKIE_SECURE=True`, `SESSION_COOKIE_HTTPONLY=True`, and HSTS enabled.

### 5. Immutable Audit Logging & Tamper-Evident SHA-256 Hash Chain

Every system access, search, record view, and clinical creation emits an **immutable `AuditLog` entry**:
- `actor`, `actor_username`, `actor_role`, `actor_hospital`
- `action` (`VIEW_PATIENT`, `CREATE_ENCOUNTER`, `BREAK_GLASS`, `AI_QUERY`, `LOGIN`, etc.)
- `patient_nhid` & `is_cross_hospital` flag
- `ip_address`, `user_agent`, `timestamp`

#### SHA-256 Hash Chain:
Each record includes a cryptographic SHA-256 digest of its canonical JSON content merged with the previous entry's hash:
```
current_hash = SHA256(prev_hash + canonical_json_fields)
```
Chain integrity can be verified at any time via:
```bash
python manage.py verify_audit_chain
```

#### Database-Level Immutability & WORM Retention:
- **SQL Immutability Triggers**: A PostgreSQL trigger (`BEFORE UPDATE OR DELETE`) blocks mutation or deletion directly at the database engine level, reinforced by Django ORM override protections (`save()`, `delete()`) and read-only admin registration.
- **Archive-then-Anchor WORM Pruning**: To prevent unbounded table growth while preserving mathematical chain continuity, `python manage.py prune_audit_logs --days=30` exports older rows into a signed WORM JSON archive (`media/audit_archives/`), publishes a cryptographic anchor receipt (`AuditLogArchiveAnchor`) to an append-only ledger (`anchor_ledger.jsonl`), and atomically prunes database records.
- **Continuous Whole-Chain Verification**: `python manage.py verify_audit_chain` validates all external WORM archives, checks ledger integrity, and bridges active database verification directly to the archive's anchor hash—guaranteeing unbroken tamper-evidence across pruning cycles.

### 6. Inter-Hospital Access Control & Break-the-Glass Workflow

Cross-hospital authorization decisions are evaluated by `can_access_patient(user, patient)`:

```
                  ┌─────────────────────────────────┐
                  │ Clinician Requests Patient View │
                  └────────────────┬────────────────┘
                                   │
                    Is User Admin or Same Hospital?
                        ┌──────────┴──────────┐
                     YES│                     │NO
                        ▼                     ▼
               ┌────────────────┐   Has Active Treatment
               │ Access Granted │   Relationship or Unexpired
               └────────────────┘   Break-Glass Access?
                                      ┌───────┴───────┐
                                   YES│               │NO
                                      ▼               ▼
                             ┌────────────────┐  ┌──────────────────┐
                             │ Access Granted │  │ Access Denied    │
                             └────────────────┘  │ Interstitial     │
                                                 └────────┬─────────┘
                                                          │
                                                Click "Break Glass"
                                                Provide Clinical Reason
                                                Confirm MFA (if active)
                                                          │
                                                          ▼
                                                 Granted 1-Hour Window
                                                 (Logged in Audit Chain)
```

1. **Auto-Treatment Relationship**: Creating an encounter automatically registers an active treatment relationship, allowing frictionless continuous care.
2. **Break-the-Glass**: For emergency care without prior history, clinicians submit a formal justification (≥ 20 characters) granting emergency access for **1 hour**, marked with prominent UI banners and flagged in audit reports.

### 7. Two-Factor Authentication (MFA / TOTP)

- Built on RFC 6238 Time-Based One-Time Passwords (TOTP), compatible with Google Authenticator, Authy, and Microsoft Authenticator.
- QR code setup with secret key generation and 8 single-use emergency backup recovery codes.
- Enforcement: When `MFA_ENFORCED=True` (or `DEBUG=False`), all clinical and administrative roles are required to complete MFA verification before accessing PHI.

### 8. Grounded Privacy-Aware AI Decision Support

- Powered by `ai/service.py` supporting **Google Gemini 2.0 Flash** or local zero-egress **Ollama** (`llama3.1:8b`).
- **Prompt Guardrails**: Uses string concatenation to prevent prompt injection and strictly enforces that answers cite source records (e.g., `[Encounter 1]`, `[Vitals 2026-01-15]`) and refuse speculative answers.

### 9. FHIR R4 Interoperability

Provides read-only FHIR R4 compliant REST endpoints:
- `GET /fhir/Patient/<NHID>/` — Standard FHIR Patient resource JSON.
- `GET /fhir/Patient/<NHID>/$everything` — Complete FHIR bundle combining Patient, Encounters, Conditions, Observations, and MedicationRequests.
- Standard coding bindings: **ICD-10** / **SNOMED CT** (Diagnoses), **LOINC** (Lab Results), and **RxNorm** (Prescriptions).

---

## Technology Stack

### Backend
- **Framework**: Python 3.13 / Django 4.2 REST API
- **Database**: Serverless PostgreSQL (Neon) / SQLite (development/testing)
- **Cryptography**: Python `cryptography` (Fernet AES-128-CBC + HMAC-SHA256)
- **Authentication & Security**: Django Auth, PyOTP, qrcode, custom RBAC & Audit Middleware
- **AI Integrations**: `google-genai` (Gemini 2.0 Flash) & Ollama local client API
- **Testing**: `pytest`, `pytest-django`, `pytest-cov`

### Frontend (SPA)
- **Framework & Build**: React 18, TypeScript, Vite 6
- **UI Component Library**: Mantine UI v7 (`@mantine/core`, `@mantine/dates`, `@mantine/notifications`, `@mantine/charts`)
- **State & Data Fetching**: TanStack React Query v5, Axios
- **Routing**: React Router v6
- **Icons**: Tabler Icons (`@tabler/icons-react`)
- **Testing**: Vitest, React Testing Library, JSDOM

---

## Architecture Diagram

```
                             ┌───────────────────────────────────────┐
                             │       Clinical User / Browser        │
                             └───────────────────┬───────────────────┘
                                                 │
                                     HTTPS / REST / JSON API
                                                 │
                                                 ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│  mEd Django Application & REST API Service                                              │
│                                                                                         │
│  ┌────────────────────────┐  ┌────────────────────────┐  ┌───────────────────────────┐  │
│  │ React 18 SPA Frontend  │  │ REST API Controllers   │  │ FHIR R4 Interoperability  │  │
│  │ (Mantine UI v7, Vite)  │  │ (/api/v1/ endpoints)   │  │ (/fhir/ Patient Bundle)   │  │
│  └────────────────────────┘  └────────────────────────┘  └───────────────────────────┘  │
│               │                          │                             │                │
│               └──────────────────────────┼─────────────────────────────┘                │
│                                          ▼                                              │
│  ┌───────────────────────────────────────────────────────────────────────────────────┐  │
│  │ Core Security & Access Engines                                                    │  │
│  │  • RBAC Permission Guards        • Field Encryption (Fernet AES-128)             │  │
│  │  • HMAC-SHA256 Blind Indexing    • SHA-256 Audit Hash Chain (Append-Only)        │  │
│  │  • Inter-Hospital & Break-Glass  • TOTP MFA Engine & Rate Limiters              │  │
│  └───────────────────────────────────────┬───────────────────────────────────────────┘  │
│                                          │                                              │
│  ┌───────────────────────────────────────┴───────────────────────────────────────────┐  │
│  │ Grounded AI Decision Support Engine                                                   │  │
│  │  • Grounded Patient Record Synthesizer (Gemini 2.0 Flash / Local Ollama llama3.1)    │  │
│  └───────────────────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────┬──────────────────────────────────────────────┘
                                           │
                                 TLS (sslmode=require)
                                           │
                                           ▼
                                ┌─────────────────────┐
                                │   PostgreSQL DB     │
                                │   (Neon Serverless) │
                                └─────────────────────┘
```

---

## Project Structure

```
mEd/
├── manage.py                     # Django management script
├── Dockerfile                    # Multi-stage production container build
├── docker-compose.yml            # Docker orchestration configuration
├── entrypoint.sh                 # Container startup & migration script
├── requirements.txt              # Backend production dependencies
├── requirements-dev.txt          # Backend development & testing tools
├── pytest.ini                    # Pytest test runner configuration
├── ruff.toml                     # Ruff Python linter configuration
│
├── accounts/                     # Custom User model, roles, MFA, auth views
├── hospitals/                    # Hospital tenancy, departments, wards, beds
├── patients/                     # Patient registry, universal NHID, blind indexes
├── records/                      # Encounters, Diagnoses, Prescriptions, Lab Results, Vitals
├── access/                       # Inter-hospital access rules, Break-Glass, TreatmentRelationships
├── audit/                        # AuditLog model, SHA-256 hash chain, triggers, prune command
├── fhir/                         # FHIR R4 JSON serializer & bundle views
├── ai/                           # Grounded AI query service (Gemini 2.0 / Ollama)
├── scheduling/                   # Appointment scheduling & booking workflows
├── referrals/                    # Inter-hospital patient referral tracking
├── shifts/                       # Staff duty rosters & shift handover management
├── patient_documents/            # Secure medical file uploads & permissions
├── core/                         # Encrypted fields, abstract models, RBAC mixins, seed script
│
├── api/                          # REST API module
│   ├── urls.py                   # API endpoint routing (/api/...)
│   ├── permissions.py            # REST permission classes
│   ├── serializers.py            # Data serialization layer
│   └── views/                    # Modular API views (auth, patients, records, vitals, etc.)
│
├── frontend/                     # Modern React SPA Frontend
│   ├── package.json              # Dependencies (React 18, Vite 6, Mantine UI v7)
│   ├── vite.config.ts            # Vite build setup & API proxy configuration
│   ├── vitest.config.ts          # Vitest unit & component test configuration
│   └── src/
│       ├── api/                  # Axios API client modules
│       ├── components/           # Reusable UI components & layouts
│       ├── context/              # Authentication & global application state
│       ├── pages/                # Page views (Dashboard, Patients, Encounters, Audit, etc.)
│       └── __tests__/            # Vitest suite (role guards, API client tests)
│
├── templates/                    # Server-rendered HTML templates (Bootstrap 5 fallback)
├── static/                       # Static CSS & JS assets
├── tests/                        # Backend Pytest suite (319 tests)
└── docs/                         # Extended academic & architecture documentation
```

---

## Quick Start (Docker)

### Prerequisites
- Docker Desktop (or Docker Engine + Docker Compose)
- A PostgreSQL database (Neon or local Postgres)

### Steps

1. **Configure Environment**
   ```bash
   cp .env.example .env
   ```
   Generate key secrets and update `.env`:
   ```env
   SECRET_KEY=<generate with: python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())">
   DEBUG=True
   DATABASE_URL=postgres://user:password@host:5432/dbname?sslmode=require
   FIELD_ENCRYPTION_KEY=<generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">
   ```

2. **Launch Application via Docker**
   ```bash
   docker compose up --build
   ```
   This process will automatically:
   - Build the backend application container.
   - Run database migrations (`python manage.py migrate`).
   - Seed initial demo hospitals, staff, patients, and encounters (`python manage.py seed_demo`).
   - Start the server on port `8000`.

3. **Access Application**
   Navigate to **`http://localhost:8000`** in your browser.

---

## Local Development

### Backend Setup (Django API)

```bash
# 1. Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# 3. Setup environment variables
cp .env.example .env
# Edit .env with your database URL and Fernet key

# 4. Run migrations & seed demo dataset
python manage.py migrate
python manage.py seed_demo

# 5. Start development server
python manage.py runserver
```

### Frontend Setup (React SPA)

```bash
# 1. Navigate to frontend directory
cd frontend

# 2. Install node dependencies
npm install

# 3. Start Vite development server
npm run dev
```
The React frontend will be available at **`http://localhost:5173`** and proxies API calls to `http://localhost:8000`.

---

## Demo Credentials

All demo accounts use the default password: **`Demo@123456`**

| Username | Role | Hospital | Typical Use Case |
|----------|------|----------|------------------|
| `admin` | `SYSTEM_ADMIN` | — | System audit log review, hash chain verification, hospital management |
| `ugmc_doctor` | `DOCTOR` | UGMC | Primary patient consultations, encounters, prescriptions, AI inquiries |
| `ugmc_nurse` | `NURSE` | UGMC | Encounter inspection, recording vitals, shift handovers |
| `kath_doctor` | `DOCTOR` | KATH | Testing inter-hospital access & emergency Break-the-Glass workflows |
| `kath_nurse` | `NURSE` | KATH | Hospital KATH clinical operations |
| `trust_lab` | `LAB_TECH` | Trust Hospital | Lab order worklist management & recording lab results |
| `ugmc_admin` | `HOSPITAL_ADMIN` | UGMC | Hospital staff onboarding & credential management |
| `ugmc_recept` | `RECEPTIONIST` | UGMC | Patient registration (attempting clinical views returns 403 Forbidden) |

---

## Demonstrating & Verifying Security Features

### 1. Role-Based Access Control (RBAC)
1. Log in as `ugmc_recept` (Receptionist).
2. Attempt to open a patient's clinical encounter in the UI or directly access an encounter endpoint such as `/api/encounters/1/` (or `/api/patients/<universal_id>/encounters/`).
3. System responds with **`403 Forbidden / Access Denied`** — Receptionists are strictly limited to registration and cannot view or manage clinical encounters.
4. Log in as `ugmc_doctor` — full clinical history is immediately accessible.

### 2. Inter-Hospital Access & Emergency Break-the-Glass
1. Log in as `kath_doctor` (Home Hospital: KATH).
2. Search for patient **Yaw Mensah** (Registered at UGMC).
3. Access is initially gated — click **"Break the Glass"**.
4. Enter clinical justification (e.g., *"Emergency trauma care required upon transfer"*) and submit.
5. Access is granted for **1 hour** with a prominent visual banner; audit entry `BREAK_GLASS` is recorded.

### 3. Field-Level Encryption at Rest Verification
1. Connect directly to your PostgreSQL database shell or SQL Console.
2. Run:
   ```sql
   SELECT universal_id, first_name, last_name FROM patients_patient LIMIT 5;
   ```
3. Observe that `first_name` and `last_name` contain base64 Fernet ciphertexts (`gAAAAA...`), confirming PHI is never stored in cleartext.

### 4. SHA-256 Audit Hash Chain Verification
1. Log in as `admin`.
2. Run the audit hash chain verification command:
   ```bash
   python manage.py verify_audit_chain
   ```
3. Command outputs `Audit log hash chain verified successfully` confirming 100% data integrity without tampering.

---

## Running Tests

The application features a comprehensive automated test suite across backend and frontend codebases (**418 automated tests**: **391** backend Pytest tests + **27** frontend Vitest tests, with 2 Postgres RLS tests skipped on SQLite).

The test suite systematically enforces core system invariants and security guarantees:
- **RBAC Boundaries & Negative Authorization**: Deny-by-default access policies across all 6 roles, strict tenant/hospital boundary scoping, and tamper-proof verification that non-clinical roles (e.g., Receptionists) cannot read or write clinical notes.
- **Field-Level Encryption Roundtrips**: Transparent Fernet (AES-128-CBC + HMAC-SHA256) encryption/decryption cycles for sensitive PII/PHI fields, key separation, and ciphertext integrity.
- **Blind Indexing & Deterministic Hashing**: Consistent search token generation without cleartext exposure or index corruption.
- **Idempotency & Concurrency Controls**: Double-submission protections and advisory lock serializations on clinical operations.
- **Break-the-Glass Emergency Flows**: Justification requirements, one-hour TTL access expiration, and mandatory audit log generation.

### Backend Test Suite (Pytest — 391 Tests)

```bash
# Run all backend unit & integration tests
pytest tests/ -v

# Run tests with coverage report
pytest tests/ --cov=. --cov-report=html
```
*Tests run against in-memory SQLite without requiring an active external database connection.*

### Frontend Test Suite (Vitest — 27 Tests)

```bash
cd frontend
npm test
```

---

## Academic & Architecture Documentation

Extended technical documentation is available in the [`docs/`](docs/) directory:

| Document | Description |
|----------|-------------|
| [`docs/requirements.md`](docs/requirements.md) | Functional & Non-Functional Requirements (NFRs) specification |
| [`docs/architecture.md`](docs/architecture.md) | System Architecture & Mermaid Sequence Diagrams |
| [`docs/data-model.md`](docs/data-model.md) | Database ERD & Complete Data Dictionary with encryption flags |
| [`docs/security-analysis.md`](docs/security-analysis.md) | STRIDE Threat Model, Mitigations & HIPAA/GDPR Compliance Matrix |
| [`docs/process-models.md`](docs/process-models.md) | BPMN Clinical Process Flow Diagrams |
| [`docs/traceability-matrix.md`](docs/traceability-matrix.md) | Requirements Traceability Matrix |
| [`docs/ROLE_BASED_USERS_PERMISSIONS_GUIDE.md`](docs/ROLE_BASED_USERS_PERMISSIONS_GUIDE.md) | Comprehensive RBAC Matrix & Permission Guide |
| [`docs/runbook.md`](docs/runbook.md) | Deployment, Maintenance & Incident Response Runbook |

### Architectural Decision Records (ADRs)

| Record | Title |
|--------|-------|
| [`ADR-001`](docs/adr/001-tenancy-model.md) | Multi-Tenancy Strategy (Single DB, Row-Level Tenancy) |
| [`ADR-002`](docs/adr/002-session-token-strategy.md) | Hybrid Session & REST Authentication Architecture |
| [`ADR-003`](docs/adr/003-fhir-adoption.md) | Adoption of FHIR R4 for Interoperability |
| [`ADR-004`](docs/adr/004-empi-approach.md) | Enterprise Master Patient Index (EMPI) Matching Strategy |
| [`ADR-005`](docs/adr/005-audit-hash-chain.md) | Cryptographic Audit Trail Hash Chaining |
| [`ADR-006`](docs/adr/006-break-glass-design.md) | Emergency Break-the-Glass Access Workflow |
| [`ADR-007`](docs/adr/007-resilience-and-async.md) | Resilience Patterns & Async Service Execution |

---

## Future Work

Key enhancements planned for future production deployments:

- **Enterprise Imprivata / SAML 2.0 SSO Integration**: Workstation single sign-on for rapid clinical login.
- **Hardware Security Module (HSM) Key Management**: Key rotation via AWS KMS / GCP Cloud KMS instead of environment variables.
- **Full SMART on FHIR Capability**: Complete FHIR read-write capabilities and launch framework integration.
- **Celery + Redis Task Queue**: Asynchronous processing for audit logs, FHIR exports, and notification alerts.
- **WebAuthn / Passkey Support**: Biometric authentication for admin and high-privilege clinical roles.
- **Patient Consent Engine**: Dynamic patient-driven consent rules blocking access to specific sensitive records.
- **Advanced Electronic Signatures (PKI / Act 772 §§11–14)**: Clinician cryptographic signing (WebCrypto / FIDO2 tokens) for drug prescriptions and diagnostic orders to achieve legal non-repudiation and Pharmacy Council compliance.

---

*Built as an academic prototype demonstrating secure system design and inter-hospital interoperability.*  
*Stack: Django 4.2 · React 18 · Mantine v7 · PostgreSQL (Neon) · Fernet Encryption · TOTP MFA · Google Gemini / Ollama · Docker*
