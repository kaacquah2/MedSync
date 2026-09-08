# MedSync EMR — Role-Based Users & Permissions Guide

## 1. System Role Architecture

MedSync uses six roles stored as lowercase snake_case values in the database.

| Role               | DB value         | Scope                        |
|--------------------|------------------|------------------------------|
| Super Admin        | `super_admin`    | Full system (all hospitals)  |
| Hospital Admin     | `hospital_admin` | One hospital, all staff/data |
| Doctor             | `doctor`         | Clinical records, AI queries |
| Nurse              | `nurse`          | Clinical records, vitals, MAR|
| Lab Technician     | `lab_technician` | Lab orders and results       |
| Receptionist       | `receptionist`   | Patient registration, appointments |

> **Implementation note:** All role comparisons use lowercase snake_case. The `User.Role` TextChoices, `api/permissions.py`, frontend `types/index.ts`, and `constants/roles.ts` all use the same values. Never hardcode `"DOCTOR"` — always import from `constants/roles.ts` on the frontend.

---

## 2. Object-Level Security & Workspace Isolation

### Patient access gate (`access/permissions.py`)
Every view that returns patient data passes the request through `can_access_patient(user, patient)`. To guarantee fail-closed security and life-safety in emergencies, gates are evaluated in the following strict priority order:

1. **admin** — `super_admin` has unrestricted system-wide access; `hospital_admin` is strictly tenant-scoped to their own hospital's registered patients.
2. **break_glass** — unexpired `BreakGlassAccess` grant (1 hour). Deliberately evaluated before consent and institutional boundaries so life-saving emergency care is never blocked by administrative barriers or consent revocations.
3. **consent_revoked** — explicitly revoked `PatientConsent` (`granted=False` or `revoked_at is not None`) denies access immediately, respecting patient privacy preferences under Ghana Data Protection Act (Act 843) even if a same-hospital or treatment relationship exists.
4. **same_hospital** — clinician's home hospital matches patient's registering hospital (`user.hospital == patient.registered_at_hospital`), provided consent was not revoked.
5. **treatment_relationship** — active, unexpired `TreatmentRelationship` exists between the clinician and patient.
6. **patient_consent** — active, explicit `PatientConsent` granted by the patient for the clinician's hospital (`granted=True`, `revoked_at is None`).
7. **denied** — all other cases fail closed (`allowed=False, basis="denied"`). Any unexpected runtime exception also fails closed with `basis="error"`.

On denial, the frontend routes the clinician to the access-denied view with an option to initiate the break-glass flow (minimum 20-character clinical justification, acknowledgment checkbox, and TOTP MFA re-verification if MFA is enforced).

### Patient consent evaluation & statutory compliance
In accordance with health data governance standards and the Ghana Data Protection Act 2012 (Act 843):
- **Opt-in / Direct Grant:** Patients can explicitly authorize specific hospitals to view their records (`PatientConsent`).
- **Revocation Precedence:** Explicit revocation immediately blocks routine clinical access and same-hospital access.
- **Emergency Exemption:** As established in emergency medical informatics ethics, Break-the-Glass (`break_glass`) strictly overrides consent revocation, logging an immutable audit record and notifying hospital administrators for retrospective review.

### Hospital workspace isolation
Staff only see data for their own hospital. Super admins see all hospitals. The `hospital` FK on `User` is the isolation boundary. New domains (appointments, referrals, wards) all filter by `user.hospital` in views.

### Audit trail
Every significant access and mutation is recorded in `AuditLog` — an append-only, tamper-evident hash chain using SHA-256. The chain is verified via:
```bash
python manage.py verify_audit_chain
# or via the super-admin UI: /superadmin/audit-logs → [Validate Chain]
```

---

## 3. Development Seed Accounts

All passwords: `Demo@123456`

| Username      | Role             | Hospital |
|---------------|------------------|----------|
| `admin`       | super_admin      | N/A      |
| `ugmc_admin`  | hospital_admin   | UGMC     |
| `ugmc_doctor` | doctor           | UGMC     |
| `ugmc_nurse`  | nurse            | UGMC     |
| `ugmc_lab`    | lab_technician   | UGMC     |
| `ugmc_recept` | receptionist     | UGMC     |
| `kath_admin`  | hospital_admin   | KATH     |
| `kath_doctor` | doctor           | KATH     |
| `kath_nurse`  | nurse            | KATH     |
| `kath_lab`    | lab_technician   | KATH     |
| `trust_admin` | hospital_admin   | TRUST    |
| `trust_doctor`| doctor           | TRUST    |
| `trust_nurse` | nurse            | TRUST    |
| `trust_lab`   | lab_technician   | TRUST    |

**Cross-hospital demo:** Log in as `kath_doctor` and open patient *Yaw Mensah* (registered at UGMC). The cross-hospital banner appears and the access is logged in the audit trail with `is_cross_hospital=True`.

---

## 4. Role-by-Role Deep Dive

### 4.1 Super Admin (`super_admin`)
**Sidebar sections:** OVERVIEW (Dashboard, System Health) · HOSPITALS (All Hospitals, Network Map) · SECURITY (Audit Logs, Break-Glass Review, User Management) · CONFIGURATION (AI Integration, Referral Network)

**Landing page:** `/superadmin`

**Exclusive UI features:**
- System-wide KPI dashboard (total hospitals, patients, encounters, cross-hospital events)
- Audit chain visualiser (`[Validate Chain]` → per-node green/red chain diagram)
- Break-glass review queue
- AI integration admin page (provider health, access matrix, guardrails)

**Key APIs:** All endpoints. `CanViewAuditLog`, `IsSystemAdmin`, `CanManageHospitals` (write).

---

### 4.2 Hospital Admin (`hospital_admin`)
**Sidebar sections:** OVERVIEW (Dashboard, Reports) · STAFF (Users, Shift Management) · FACILITY (Wards & Beds, Audit Logs) · MONITORING (Admissions, Appointments, Alerts, Referrals)

**Landing page:** `/` (Hospital Overview Dashboard)

**Exclusive UI features:**
- Wards & Beds management (`/admin/facilities`) — ward cards with bed grid and occupancy progress
- Staff management (create/edit/deactivate staff for own hospital)
- Hospital-scoped audit logs

**Key APIs:** `CanManageStaff`, `CanManageWards`, `IsHospitalAdmin`.

---

### 4.3 Doctor (`doctor`)
**Sidebar sections:** CLINICAL (Dashboard, My Worklist, Emergency Queue) · PATIENTS (Search Patients, Appointments) · NETWORK (Referrals, Inter-Hospital) · ALERTS

**Landing page:** `/` (Clinical Dashboard with encounter stats)

**Exclusive UI features:**
- `[Add Record ▼]` menu on patient chart (New Encounter, Add Alert/Allergy)
- `[Query Patient Records]` AI button on patient chart
- Prescription creation
- Referral creation
- Diagnosis creation

**Key APIs:** `CanCreateEncounter`, `CanPrescribe`, `CanRecordVitals`, `CanOrderLabTest`, `CanManageReferrals`, `CanQueryAI`.

---

### 4.4 Nurse (`nurse`)
**Sidebar sections:** WARD (Dashboard, My Ward, Emergency) · SHIFTS (Handover) · ALERTS

**Landing page:** `/` (Nursing Dashboard with encounter/alert stats)

**Exclusive UI features:**
- Shift start/end (`/shifts/start/`, `/shifts/<id>/end/`)
- Shift handover notes (`/worklist/handover`)
- MAR administration (nurse-interactive cells in patient chart MAR tab)
- Vital signs recording

**Key APIs:** `CanCreateEncounter`, `CanRecordVitals`, `CanAdministerMedication`, `CanManageShifts`, `CanQueryAI`.

---

### 4.5 Lab Technician (`lab_technician`)
**Sidebar sections:** LABORATORY (Dashboard, Order Worklist, Results)

**Landing page:** `/` (Lab Dashboard with results stats)

**Exclusive UI features:**
- Lab order worklist (`/lab/orders`) with STAT indicator and Start/Mark Resulted buttons
- Status transitions: pending → in_progress → resulted

**Key APIs:** `CanResultLabOrder`, `CanCreateLabResult`, `IsAdminOrClinical`.

---

### 4.6 Receptionist (`receptionist`)
**Sidebar sections:** FRONT DESK (Dashboard, Appointments, Patient Directory, Emergency Queue)

**Landing page:** `/` (Reception Dashboard with patient registration stats)

**Exclusive UI features:**
- Appointment check-in / no-show / cancel actions
- Patient registration
- Today's appointment table with status action buttons

**Key APIs:** `CanRegisterPatient`, `CanManageAppointments`.

---

## 5. Tab Visibility Matrix (Patient Chart)

| Tab            | Doctor | Nurse | Lab Tech | Receptionist | Hospital Admin | Super Admin |
|----------------|--------|-------|----------|--------------|----------------|-------------|
| Overview       | ✓      | ✓     | ✓        | ✓            | ✓              | ✓           |
| Encounters     | ✓      | ✓     | ✓        | ✓            | ✓              | ✓           |
| Diagnoses      | ✓      | ✓     |          |              | ✓              | ✓           |
| Prescriptions  | ✓      | ✓     |          |              | ✓              | ✓           |
| Labs           | ✓      | ✓     | ✓        |              | ✓              | ✓           |
| Vitals         | ✓      | ✓     |          |              | ✓              | ✓           |
| MAR            | ✓(R)   | ✓(W)  |          |              |                |             |
| [Query AI]     | ✓      | ✓     |          |              | ✓              | ✓           |
| [Export FHIR]  | ✓      |       |          |              | ✓              | ✓           |

Legend: ✓ = read access · (W) = write/interactive · (R) = read-only

---

## 6. API Endpoint Permissions Matrix

| Endpoint                                    | Roles                                           |
|---------------------------------------------|-------------------------------------------------|
| `GET /api/patients/`                        | All authenticated                               |
| `POST /api/patients/new/`                   | doctor, nurse, receptionist, hospital_admin, super_admin |
| `GET /api/patients/<nhid>/`                 | + `can_access_patient` gate                     |
| `POST /api/patients/<nhid>/break-glass/`    | All authenticated (clinical intent)             |
| `GET/POST /api/patients/<nhid>/vitals/`     | GET: all with access · POST: doctor, nurse      |
| `GET/POST /api/patients/<nhid>/lab-orders/` | GET: all with access · POST: doctor, nurse      |
| `GET /api/lab-orders/worklist/`             | lab_technician, doctor, nurse, hospital_admin, super_admin |
| `PATCH /api/lab-orders/<id>/status/`        | lab_technician, doctor, nurse                   |
| `GET/POST /api/appointments/`               | receptionist, doctor, nurse, hospital_admin, super_admin |
| `POST /api/appointments/<id>/status/`       | receptionist, doctor, nurse, hospital_admin, super_admin |
| `GET/POST /api/referrals/`                  | doctor, hospital_admin, super_admin             |
| `GET/POST /api/wards/`                      | GET: all · POST: hospital_admin, super_admin    |
| `PATCH /api/beds/<id>/status/`              | hospital_admin, super_admin                     |
| `GET /api/shifts/`                          | nurse, hospital_admin, super_admin              |
| `POST /api/shifts/start/`                   | nurse, hospital_admin, super_admin              |
| `PATCH /api/shifts/<id>/end/`               | nurse (own), hospital_admin, super_admin        |
| `GET/POST /api/handovers/`                  | nurse, hospital_admin, super_admin              |
| `GET /api/alerts/`                          | All authenticated                               |
| `GET /api/audit/`                           | super_admin                                     |
| `POST /api/audit/validate-chain/`           | super_admin                                     |
| `POST /api/patients/<nhid>/ai-query/`       | doctor, nurse, hospital_admin, super_admin      |

---

## 7. AI Access Control Matrix

| Role             | Can Query AI | Context Grounding     | Audit Action |
|------------------|--------------|-----------------------|--------------|
| Super Admin      | ✓            | All authorised records| `AI_QUERY`   |
| Hospital Admin   | ✓            | All authorised records| `AI_QUERY`   |
| Doctor           | ✓            | Authorised records    | `AI_QUERY`   |
| Nurse            | ✓            | Authorised records    | `AI_QUERY`   |
| Lab Technician   | ✗            | N/A                   | N/A          |
| Receptionist     | ✗            | N/A                   | N/A          |

### AI Provider Options
| Provider | Free | PHI Egress | Setup & Compliance |
|----------|------|------------|---------------------|
| Local Ollama (`llama3.1:8b`) (Production Default) | ✓ (compute only) | **No** — fully local | `AI_PROVIDER=ollama` + Ollama installed (HIPAA & Ghana DPA compliant) |
| Gemini 2.5 Flash (Dev/Test Only) | ✓ (1,500 req/day) | Yes (to Google) | `GEMINI_API_KEY=...` in `.env` (Blocked in production / `DEBUG=False`) |

---

## 8. Design System Reference

### Mantine Theme Tokens (from `frontend/src/main.tsx`)

| Token            | Value       | Usage                               |
|------------------|-------------|-------------------------------------|
| `medsync[5]`     | `#1a56db`   | Primary brand blue (buttons, active nav) |
| `medsync[0]`     | `#e8f0fe`   | Light blue (hover, selected rows)   |
| `clinical[5]`    | `#057a55`   | Success green (normal lab, active)  |
| `danger[5]`      | `#c81e1e`   | Alert red (abnormal, high-risk)     |
| `warn[5]`        | `#c27803`   | Warning amber (cross-hospital, overdue) |

### Role Colours (from `frontend/src/constants/roles.ts`)

| Role             | Mantine colour |
|------------------|----------------|
| `super_admin`    | `red`          |
| `hospital_admin` | `orange`       |
| `doctor`         | `blue`         |
| `nurse`          | `teal`         |
| `lab_technician` | `violet`       |
| `receptionist`   | `gray`         |

---

## 9. Running the Demo

```bash
# Start the Django dev server
python manage.py migrate
python manage.py seed_demo
python manage.py runserver

# In a second terminal — start the Vite dev server
cd frontend && npm run dev

# Navigate to: http://localhost:5173/spa/login
# All accounts use password: Demo@123456
```

### Demo script for the cross-hospital + AI scenario
1. Log in as `ugmc_doctor` → observe the Clinical Dashboard
2. Search for patient *Yaw Mensah* (UGMC patient — `same_hospital` access)
3. Click **Query Patient Records** → ask: *"What is this patient's allergy history and most recent lab results?"*
4. Log out → log in as `kath_doctor`
5. Search for *Yaw Mensah* (UGMC patient from KATH hospital) → see cross-hospital banner
6. Log in as `admin` → go to `/superadmin/audit-logs` → see `VIEW_PATIENT` + `AI_QUERY` entries with `is_cross_hospital=True`
7. Click **[Validate Chain]** → see all-green nodes confirming chain integrity
