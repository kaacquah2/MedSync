# User Manual — mEd EMR

Quick-start guide for each staff role. All actions assume you are logged in.

---

## All roles — common tasks

### Logging in
Navigate to `/accounts/login/`. Enter your username and password. If your role requires MFA (Doctor, Nurse, Lab Technician, Hospital Admin, System Admin), you will be prompted for your authenticator app code. Receptionists are not required to use MFA.

### Finding a patient
- **Keyboard shortcut:** press `/` to focus the search bar in the top navigation bar.
- Type an NHID (e.g. `NHID-A1B2C3D4`) for an exact lookup, or a patient name for a fuzzy search.
- Results from **all hospitals** are returned — this is by design. Opening a cross-hospital record requires an access relationship; a warning banner will appear if you do not have one.

### Your profile and security
Click your name in the top-right corner → **Profile**. From there you can:
- Update your name, contact details, and bio.
- Change your password.
- View your MFA status, see how many recovery codes remain, and regenerate codes.
- Sign out of all other devices (e.g. if you left a session open on another workstation).

---

## Receptionist

**Can:** search patients; register new patients; view patient records (read-only).  
**Cannot:** create encounters, diagnoses, prescriptions, or lab results.

### Registering a new patient
1. Sidebar → **Register Patient** (or navbar search → **New Patient** button).
2. Fill in all fields. The NHID is assigned automatically.
3. If the system detects a probable duplicate (same name+DOB), you will be warned. Review the candidate match before confirming a new registration.
4. Save — the new patient's record opens immediately.

---

## Doctor

**Can:** everything a Nurse can, plus prescriptions. Also: record allergies/alerts.

### Opening an encounter
1. Open the patient record → **New encounter**.
2. Select encounter type, enter chief complaint and clinical notes → Save.

### Recording a diagnosis
1. From the encounter detail → **Add Diagnosis**.
2. Enter an ICD-10 code (start typing in the code field — common codes appear as suggestions) and a description.
3. Save → you return to the encounter at the Diagnoses section.

### Prescribing medication
1. Encounter detail → **Add Prescription**.
2. Enter drug name, dosage, frequency, and any instructions.
3. A **confirmation screen** shows the prescription summary — check the patient's allergy strip at the top before confirming.
4. Click **Confirm & prescribe** to save.

### Recording an allergy or clinical alert
1. Patient detail → **Record alert/allergy**.
2. Choose type (Allergy or Clinical Alert), enter the substance/description, severity, and any reaction notes.
3. Save — the alert appears immediately in the patient banner on every sub-page, visible to all clinicians including those at other hospitals.

---

## Nurse

**Can:** open encounters; add diagnoses; add lab results; record allergies/alerts.  
**Cannot:** prescribe medication.

Same workflow as Doctor for encounters, diagnoses, and alerts. For lab results (if you are collecting samples): encounter detail → **Add Lab Result**.

---

## Laboratory Technician

**Can:** view patient records (subject to access gate); add lab results.  
**Cannot:** open encounters, diagnoses, or prescriptions; register patients.

### Adding a lab result
1. Open the patient record (search by NHID or name).
2. Open the relevant encounter → **Add Lab Result**.
3. Enter test name, result value, reference range, and whether the result is abnormal.
4. Save → you return to the encounter at the Lab Results section.

---

## Hospital Administrator

**Can:** manage staff accounts at your hospital; view all patient records and audit data for your hospital.

### Adding a new staff member
Sidebar → **Administration → Staff → Add Staff**. Complete the form. The new user's password must meet the 12-character minimum policy. You cannot create System Administrator accounts.

### Deactivating a departing staff member (leaver process)
1. Sidebar → **Administration → Staff**.
2. On the departing clinician's row, click the **Deactivate** button (person-minus icon).
3. Confirm. Their active sessions are terminated immediately — they cannot continue working. The account is preserved for audit purposes.

### Reactivating an account
Click the **Activate** button on the same row.

---

## System Administrator

**Can:** everything above, plus: manage hospitals; view the full audit log; access Django admin.

### Reviewing break-glass access
Sidebar → **Security → Audit Log** → filter Action = **Break-Glass Override**. Review each event; see `docs/break-glass-review-process.md` for the review protocol.

### Viewing disclosures for a specific patient
Open the patient record → **Disclosures** button (top-right, visible to SYSTEM_ADMIN only). This opens the audit log filtered to that patient's NHID.

### Verifying audit-log integrity
```bash
python manage.py verify_audit_chain
```

### Rotating encryption keys
See `docs/runbook.md` §2 for the full key-rotation procedure.

---

## Cross-hospital access (all clinical roles)

If you try to open a patient from another hospital without a care relationship:
1. You will see an **Access Restricted** screen.
2. You can invoke **break-glass** (emergency override): provide a clinical justification (at least 20 characters), tick the acknowledgement, and optionally re-confirm your TOTP code.
3. Emergency access lasts **1 hour** and is reviewed by administrators.

If you are treating a referred patient or a patient who presented at your hospital, your access is automatically extended via a Treatment Relationship when you open an encounter — future visits will not require break-glass.
