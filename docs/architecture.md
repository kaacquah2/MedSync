# Architecture & Sequence Diagrams — mEd Secure Centralised EMR System

## 1. Component Diagram

```mermaid
graph TB
    subgraph Clients["Clinical Users (Browser)"]
        HospA["Hospital A Staff\n(Doctor, Nurse, Admin)"]
        HospB["Hospital B Staff\n(Doctor, Nurse, Admin)"]
        HospC["Hospital C Staff\n(Receptionist)"]
    end

    subgraph Application["Django Application (Gunicorn)"]
        direction TB
        MW["Middleware Stack\n────────────────────\nSecurityMiddleware\nSessionMiddleware\nAuthenticationMiddleware\nOTPMiddleware (django-otp)\nAxesMiddleware (lockout)\nAuditMiddleware\nMFAEnforcementMiddleware"]
        RBAC["RBAC Layer\n────────────────────\n@role_required decorator\nRoleRequiredMixin\n6 roles enforced per view"]
        Apps["App Layer\n────────────────────\ncore / accounts\nhospitals / patients\nrecords / audit"]
        Enc["Encryption Layer\n────────────────────\nEncryptedCharField\nEncryptedTextField\nFernet (AES-128-CBC)"]
        BI["Blind-Index Layer\n────────────────────\nmake_blind_index()\nHMAC-SHA256 keyed hash"]
    end

    subgraph DB["Neon (Serverless PostgreSQL)"]
        Tables["Tables\n────────────────────\nhospitals_hospital\naccounts_user\npatients_patient ← encrypted\nrecords_encounter ← encrypted\nrecords_diagnosis ← encrypted\nrecords_prescription ← encrypted\nrecords_labresult ← encrypted\naudit_auditlog (append-only)"]
    end

    Clients -- "HTTPS (TLS 1.3)" --> Application
    Application -- "TLS sslmode=require" --> DB
    MW --> RBAC --> Apps --> Enc --> DB
    Apps --> BI --> DB
```

---

## 2. Sequence Diagram: Login + MFA Verification

This shows the full login flow when `MFA_ENFORCED=True` for a clinical user.

```mermaid
sequenceDiagram
    actor User as Clinician (Doctor)
    participant Browser
    participant Django as Django App
    participant DB as Neon DB
    participant Audit as AuditLog

    User->>Browser: Navigate to /accounts/login/
    Browser->>Django: GET /accounts/login/
    Django-->>Browser: Login form

    User->>Browser: Enter username + password
    Browser->>Django: POST /accounts/login/
    Django->>DB: SELECT user WHERE username=?
    DB-->>Django: User record

    alt Correct password (≤5 failures)
        Django->>DB: CREATE AuditLog(action=LOGIN, actor=user)
        Django-->>Browser: Redirect to /
        Browser->>Django: GET /  (dashboard)
        Django->>Django: MFAEnforcementMiddleware checks\n[user is authenticated, role=DOCTOR,\nMFA_ENFORCED=True]
        Django->>DB: SELECT TOTPDevice WHERE user=? AND confirmed=True
        DB-->>Django: No device found
        Django-->>Browser: Redirect to /accounts/mfa/setup/
        Browser->>Django: GET /accounts/mfa/setup/
        Django->>DB: CREATE TOTPDevice(confirmed=False)
        Django-->>Browser: QR code + code entry form

        User->>Browser: Scan QR with Authenticator App
        User->>Browser: Enter 6-digit TOTP code
        Browser->>Django: POST /accounts/mfa/setup/ {code}
        Django->>Django: device.verify_token(code)
        alt Code correct
            Django->>DB: UPDATE TOTPDevice SET confirmed=True
            Django->>DB: CREATE AuditLog(action=MFA_ENROLLED)
            Django->>Django: session['otp_verified'] = True
            Django-->>Browser: Redirect to Dashboard ✓
        else Code wrong
            Django-->>Browser: Error — try again
        end

    else Wrong password (≥5 failures)
        Django->>DB: axes: record failure, lock account
        Django->>DB: CREATE AuditLog(action=ACCESS_DENIED, reason=brute_force)
        Django-->>Browser: 403 Account Locked page
    end
```

---

## 3. Sequence Diagram: Cross-Hospital Patient Access with Audit Flag

This is the core inter-hospital access scenario. A Doctor at Hospital B accesses
a patient whose records were created at Hospital A.

```mermaid
sequenceDiagram
    actor DocB as Dr. Sarpong (Hospital B / KATH)
    participant Browser
    participant Django as Django App
    participant DB as Neon DB
    participant Audit as AuditLog

    Note over DocB: Logged in and MFA verified (session['otp_verified']=True)

    DocB->>Browser: Search "NHID-A1B2C3D4"
    Browser->>Django: GET /patients/?query=NHID-A1B2C3D4
    Django->>DB: SELECT patient WHERE universal_id='NHID-A1B2C3D4'
    Note over DB: No full-table decrypt — NHID is indexed plaintext
    DB-->>Django: Patient (registered_at_hospital=UGMC)
    Django-->>Browser: Search results

    DocB->>Browser: Click "View" on patient
    Browser->>Django: GET /patients/NHID-A1B2C3D4/
    Django->>Django: Check auth (✓) + role (DOCTOR ✓)
    Django->>DB: SELECT patient WHERE universal_id=?
    DB-->>Django: Patient (encrypted fields)
    Django->>Django: Decrypt PII fields using FIELD_ENCRYPTION_KEY
    Django->>Django: Compute is_cross_hospital:\n  DocB.hospital(KATH) ≠ patient.registered_at_hospital(UGMC)\n  → is_cross_hospital = TRUE

    Django->>DB: CREATE AuditLog(\n  actor=DocB, role=DOCTOR,\n  actor_hospital='KATH',\n  action=VIEW_PATIENT,\n  patient_nhid='NHID-A1B2C3D4',\n  is_cross_hospital=TRUE,\n  ip_address=...\n)
    Note over Audit: Immutable entry created

    Django->>DB: SELECT encounters WHERE patient=? (all hospitals)
    DB-->>Django: Encounters from UGMC and KATH
    Django-->>Browser: Patient detail with ⚠️ cross-hospital banner\nand full encounter timeline

    Note over DocB: Banner: "Cross-hospital access.\nThis patient is registered at UGMC.\nThis access has been logged."

    rect rgb(255, 240, 240)
        Note over Audit: System Admin can now see:\naudit log entry with is_cross_hospital=TRUE
    end
```

---

## 4. Sequence Diagram: Encrypted Write / Read Path

This shows how PII flows through the encryption layer when creating and
subsequently reading a patient record.

```mermaid
sequenceDiagram
    actor Nurse as Nurse (Hospital A)
    participant Browser
    participant Django as Django App
    participant Fields as EncryptedCharField\n(core/fields.py)
    participant Fernet as Fernet (cryptography)
    participant DB as Neon DB

    Note over Nurse: Registering a new patient

    Nurse->>Browser: Fill patient form\n(first_name="Yaw", dob="1985-03-12", ...)
    Browser->>Django: POST /patients/new/

    Django->>Fields: patient.first_name = "Yaw"
    Fields->>Fernet: encrypt_value("Yaw")\nusing FIELD_ENCRYPTION_KEY
    Fernet-->>Fields: "gAAAAA..." (ciphertext)
    Fields-->>Django: store "gAAAAA..."

    Django->>Fields: Compute name_hash\nmake_blind_index("Yaw Mensah")
    Fields-->>Django: HMAC-SHA256 hex digest

    Django->>DB: INSERT INTO patients_patient\n(first_name='gAAAAA...', name_hash='abc123...')
    Note over DB: Database stores ONLY ciphertext and HMAC hash.\nNo plaintext ever persists.
    DB-->>Django: id=42, universal_id='NHID-A1B2C3D4'
    Django-->>Browser: Redirect to patient detail

    Note over Nurse: Later — reading the patient record

    Nurse->>Browser: View patient NHID-A1B2C3D4
    Browser->>Django: GET /patients/NHID-A1B2C3D4/
    Django->>DB: SELECT * FROM patients_patient WHERE universal_id='NHID-A1B2C3D4'
    DB-->>Django: (first_name='gAAAAA...', name_hash='abc123...')

    Django->>Fields: from_db_value('gAAAAA...')
    Fields->>Fernet: decrypt_value("gAAAAA...")\nusing FIELD_ENCRYPTION_KEY
    Fernet-->>Fields: "Yaw" (plaintext)
    Fields-->>Django: patient.first_name = "Yaw"

    Django-->>Browser: Patient detail page\ndisplaying "Yaw Mensah"
```

---

## 5. Deployment Architecture (Docker + Neon)

```mermaid
graph LR
    subgraph Local / Server
        DC["docker-compose.yml"]
        subgraph Container["Docker Container (med-emr)"]
            G["Gunicorn\n(2 workers)"]
            DJ["Django 4.2 App"]
        end
    end

    subgraph Neon["Neon (Cloud)"]
        PG["PostgreSQL\n(TLS enforced)\n(storage encrypted)"]
    end

    DC --> Container
    G --> DJ
    DJ -- "TLS sslmode=require" --> PG
    User["Browser"] -- "HTTP :8000" --> G

    style Neon fill:#e8f4fd,stroke:#0d6efd
    style Container fill:#e8ffe8,stroke:#198754
```

---

## 6. Data Flow: Search with Blind Index

```mermaid
flowchart TD
    A[User types query in search box] --> B{Query starts with NHID-?}

    B -- Yes --> C[SQL: SELECT WHERE universal_id = query\nO log n — DB index]
    B -- No --> D[Compute HMAC-SHA256 of query\nusing BLIND_INDEX_KEY]
    D --> E[SQL: SELECT WHERE name_hash = hmac\nO log n — DB index]
    E --> F{Any exact matches?}
    F -- Yes --> G[Return indexed results]
    F -- No, or query < 5 chars --> H[Python-side partial scan\nLoad all → decrypt → filter\nO n — documented limitation]

    C --> I[Display results]
    G --> I
    H --> I

    style H fill:#fff3cd,stroke:#ffc107
    style C fill:#d4edda,stroke:#28a745
    style E fill:#d4edda,stroke:#28a745
```
