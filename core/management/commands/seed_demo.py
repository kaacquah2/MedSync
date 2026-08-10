"""
seed_demo - populate the database with demo hospitals, staff, patients, and
            cross-hospital encounters for immediate demonstration.

Idempotent: running it twice will not create duplicates (it uses get_or_create).

Usage:
    python manage.py seed_demo

Demo credentials (all passwords = Demo@123456):
    System Admin : admin / Demo@123456
    UGMC Doctor  : ugmc_doctor / Demo@123456
    KATH Nurse   : kath_nurse  / Demo@123456
    TRUST LabTech: trust_lab   / Demo@123456
    ... (see full list printed at the end of seed_demo)
"""

from django.core.management.base import BaseCommand

DEMO_PASSWORD = "Demo@123456"

HOSPITALS = [
    {
        "name": "University of Ghana Medical Centre",
        "code": "UGMC",
        "city": "Accra",
        "country": "Ghana",
    },
    {
        "name": "Komfo Anokye Teaching Hospital",
        "code": "KATH",
        "city": "Kumasi",
        "country": "Ghana",
    },
    {"name": "Trust Hospital", "code": "TRUST", "city": "Accra", "country": "Ghana"},
]

# (username, first_name, last_name, role, hospital_code)
STAFF = [
    # System-wide admin (no hospital)
    ("admin", "System", "Admin", "super_admin", None),
    # UGMC staff
    ("ugmc_admin", "Agnes", "Mensah", "hospital_admin", "UGMC"),
    ("ugmc_doctor", "Kwame", "Asante", "doctor", "UGMC"),
    ("ugmc_nurse", "Abena", "Osei", "nurse", "UGMC"),
    ("ugmc_lab", "Kofi", "Boateng", "lab_technician", "UGMC"),
    ("ugmc_reception", "Akua", "Darko", "receptionist", "UGMC"),
    # KATH staff
    ("kath_admin", "Yaw", "Appiah", "hospital_admin", "KATH"),
    ("kath_doctor", "Ama", "Sarpong", "doctor", "KATH"),
    ("kath_nurse", "Efia", "Dankwa", "nurse", "KATH"),
    ("kath_lab", "Nana", "Frimpong", "lab_technician", "KATH"),
    # TRUST staff
    ("trust_admin", "Adjoa", "Amoah", "hospital_admin", "TRUST"),
    ("trust_doctor", "Kweku", "Poku", "doctor", "TRUST"),
    ("trust_nurse", "Akosua", "Antwi", "nurse", "TRUST"),
    ("trust_lab", "Fiifi", "Addai", "lab_technician", "TRUST"),
]

# (first_name, last_name, dob, sex, blood_group, national_id, phone, address, registered_at_code)
PATIENTS = [
    (
        "Yaw",
        "Mensah",
        "1985-03-12",
        "M",
        "A+",
        "GHA-001-001",
        "+233244001001",
        "12 Ring Road Central, Accra",
        "UGMC",
    ),
    (
        "Akosua",
        "Owusu",
        "1992-07-24",
        "F",
        "O+",
        "GHA-001-002",
        "+233244001002",
        "45 Adum Street, Kumasi",
        "KATH",
    ),
    (
        "Emmanuel",
        "Boateng",
        "1970-11-05",
        "M",
        "B+",
        "GHA-001-003",
        "+233244001003",
        "8 Liberation Road, Accra",
        "TRUST",
    ),
    (
        "Abena",
        "Asante",
        "2001-01-30",
        "F",
        "AB-",
        "GHA-001-004",
        "+233244001004",
        "22 Hospital Road, Kumasi",
        "KATH",
    ),
    (
        "Kwame",
        "Darko",
        "1998-06-15",
        "M",
        "O-",
        "GHA-001-005",
        "+233244001005",
        "5 Independence Ave, Accra",
        "UGMC",
    ),
]


class Command(BaseCommand):
    help = "Seed the database with demo hospitals, staff, patients, and encounters."

    def handle(self, *args, **options):
        import os

        from django.conf import settings

        # ── RLS bypass ───────────────────────────────────────────────────────
        # seed_demo reads from RLS-protected tables (records_encounter via
        # Encounter.objects.filter/get_or_create, and audit_auditlog via
        # AuditLog.objects.filter).  Management commands run without a request
        # context so the middleware GUCs are not set.  We enable the bypass
        # at session level; it persists for the lifetime of this process.
        from django.db import connection as _dbc

        if _dbc.vendor == "postgresql":
            with _dbc.cursor() as _cur:
                _cur.execute("SELECT set_config('app.bypass_rls', 'on', false)")

        from accounts.models import User
        from hospitals.models import Hospital
        from patients.models import Patient, PatientAlert
        from records.models import Diagnosis, Encounter, LabResult, Prescription

        # ── Production guard ──────────────────────────────────────────────────
        # seed_demo creates accounts with the publicly-known DEMO_PASSWORD.
        # Refuse to set usable passwords in production unless an explicit
        # override flag is set.  The entrypoint gates the whole command behind
        # SEED_DEMO=true, but this guard protects against running it manually.
        allow_usable_pw = settings.DEBUG or os.environ.get("SEED_DEMO_ALLOW_SUPERUSER") == "true"

        if not allow_usable_pw:
            self.stderr.write(
                self.style.WARNING(
                    "\nWARNING: DEBUG=False detected.  seed_demo will create accounts\n"
                    "WITHOUT usable passwords (set_unusable_password).  Staff must\n"
                    "have their passwords set via 'manage.py changepassword <username>'\n"
                    "before they can log in.\n"
                    "Set SEED_DEMO_ALLOW_SUPERUSER=true to override (not recommended).\n"
                )
            )

        self.stdout.write(self.style.MIGRATE_HEADING("\n=== Seeding demo data ===\n"))

        # ── 1. Hospitals ──────────────────────────────────────────────────
        hospital_map = {}
        for data in HOSPITALS:
            h, created = Hospital.objects.get_or_create(
                code=data["code"],
                defaults={k: v for k, v in data.items() if k != "code"},
            )
            hospital_map[data["code"]] = h
            self.stdout.write(f"  {'+ Created' if created else '  Exists '} Hospital: {h}")

        # ── 2. Staff / Users ──────────────────────────────────────────────
        user_map = {}
        for username, first, last, role, hosp_code in STAFF:
            hospital = hospital_map.get(hosp_code) if hosp_code else None
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "first_name": first,
                    "last_name": last,
                    "role": role,
                    "hospital": hospital,
                    "email": f"{username}@med.demo",
                    "is_staff": role == "super_admin",
                    "is_superuser": role == "super_admin",
                },
            )
            if created:
                if allow_usable_pw:
                    user.set_password(DEMO_PASSWORD)
                else:
                    # In production, never set the public demo password.
                    # Accounts are created but cannot be logged into until a
                    # real password is assigned via 'manage.py changepassword'.
                    user.set_unusable_password()
                user.save()
            user_map[username] = user
            self.stdout.write(
                f"  {'+ Created' if created else '  Exists '} User: {username} ({role})"
            )

        # ── 3. Patients ───────────────────────────────────────────────────
        from core.blind_index import make_blind_index

        patient_list = []
        for first, last, dob, sex, bg, nid, phone, address, reg_code in PATIENTS:
            # Dedup via blind-index - O(log n) indexed lookup instead of full scan
            nid_hash = make_blind_index(nid)
            existing = Patient.objects.filter(national_id_hash=nid_hash).first()

            if existing:
                patient_list.append(existing)
                self.stdout.write(f"  Exists   Patient: {first} {last} ({existing.universal_id})")
            else:
                registrar_username = {
                    "UGMC": "ugmc_reception",
                    "KATH": "kath_admin",
                    "TRUST": "trust_admin",
                }.get(reg_code, "admin")
                patient = Patient.objects.create(
                    first_name=first,
                    last_name=last,
                    date_of_birth=dob,
                    sex=sex,
                    blood_group=bg,
                    national_id=nid,
                    phone=phone,
                    address=address,
                    registered_at_hospital=hospital_map[reg_code],
                    registered_by=user_map[registrar_username],
                )
                patient_list.append(patient)
                self.stdout.write(f"  + Created Patient: {first} {last} ({patient.universal_id})")

        # ── 4. Encounters (with cross-hospital scenario) ───────────────────
        if len(patient_list) >= 3:
            patient_yaw = patient_list[0]  # registered at UGMC
            patient_akosua = patient_list[1]  # registered at KATH
            patient_emmanuel = patient_list[2]  # registered at TRUST

            ugmc_doc = user_map["ugmc_doctor"]
            kath_doc = user_map["kath_doctor"]
            _trust_doc = user_map["trust_doctor"]  # noqa: F841 (used implicitly via user_map)
            ugmc_nurse = user_map["ugmc_nurse"]
            kath_lab = user_map["kath_lab"]

            def make_encounter(patient, doc, hospital, etype, complaint, notes=""):
                """Create encounter if this patient doesn't already have one at this hospital."""
                existing = Encounter.objects.filter(
                    patient=patient,
                    created_by=doc,
                    created_at_hospital=hospital,
                    encounter_type=etype,
                ).first()
                if existing:
                    return existing, False
                enc = Encounter.objects.create(
                    patient=patient,
                    encounter_type=etype,
                    chief_complaint=complaint,
                    notes=notes,
                    created_by=doc,
                    created_at_hospital=hospital,
                )
                return enc, True

            encounters_created = 0

            # Encounter 1: Yaw's OPD at UGMC (his home hospital)
            enc1, created = make_encounter(
                patient_yaw,
                ugmc_doc,
                hospital_map["UGMC"],
                "OPD",
                "Persistent headache and fever for 3 days.",
                "Patient appears febrile. Temp 38.5°C. BP 120/80.",
            )
            if created:
                encounters_created += 1
                Diagnosis.objects.create(
                    encounter=enc1,
                    icd_code="R51.9",
                    description="Headache, unspecified. Possible malaria - test ordered.",
                    is_primary=True,
                    created_by=ugmc_doc,
                )
                Prescription.objects.create(
                    encounter=enc1,
                    drug_name="Paracetamol 500mg",
                    dosage="500mg oral",
                    frequency="Every 6 hours for 3 days",
                    created_by=ugmc_doc,
                )
                LabResult.objects.create(
                    encounter=enc1,
                    test_name="Malaria RDT",
                    result_value="Positive - Plasmodium falciparum detected",
                    is_abnormal=True,
                    created_by=ugmc_nurse,
                )
                self.stdout.write("  + Created Encounter: Yaw @ UGMC (home hospital)")

            # Encounter 2: Akosua's follow-up at KATH (her home hospital)
            enc2, created = make_encounter(
                patient_akosua,
                kath_doc,
                hospital_map["KATH"],
                "FU",
                "Follow-up for hypertension management.",
                "BP controlled at 130/85. Medications tolerated.",
            )
            if created:
                encounters_created += 1
                Diagnosis.objects.create(
                    encounter=enc2,
                    icd_code="I10",
                    description="Essential hypertension - well controlled.",
                    is_primary=True,
                    created_by=kath_doc,
                )
                Prescription.objects.create(
                    encounter=enc2,
                    drug_name="Amlodipine 5mg",
                    dosage="5mg oral",
                    frequency="Once daily",
                    created_by=kath_doc,
                )
                self.stdout.write("  + Created Encounter: Akosua @ KATH (home hospital)")

            # ── Cross-hospital scenario ──────────────────────────────────
            # Yaw (registered at UGMC) presents at KATH with chest pain.
            # kath_doctor (KATH) accesses a UGMC patient -> cross-hospital.
            enc3, created = make_encounter(
                patient_yaw,
                kath_doc,
                hospital_map["KATH"],
                "EMRG",
                "Acute chest pain, shortness of breath.",
                "Patient transferred from UGMC. History of malaria last month. ECG shows ST changes.",
            )
            if created:
                encounters_created += 1
                Diagnosis.objects.create(
                    encounter=enc3,
                    icd_code="I21.9",
                    description="Suspected acute myocardial infarction.",
                    is_primary=True,
                    created_by=kath_doc,
                )
                LabResult.objects.create(
                    encounter=enc3,
                    test_name="Troponin I",
                    result_value="0.45 ng/mL (elevated)",
                    reference_range="< 0.04 ng/mL",
                    is_abnormal=True,
                    created_by=kath_lab,
                )
                self.stdout.write("  + Created Cross-hospital Encounter: Yaw (UGMC patient) @ KATH")

            # Emmanuel (TRUST patient) seen at UGMC - another cross-hospital encounter
            enc4, created = make_encounter(
                patient_emmanuel,
                ugmc_doc,
                hospital_map["UGMC"],
                "OPD",
                "Chronic diabetes management review.",
                "Patient transferred records from Trust Hospital. HbA1c stable.",
            )
            if created:
                encounters_created += 1
                Diagnosis.objects.create(
                    encounter=enc4,
                    icd_code="E11.9",
                    description="Type 2 diabetes mellitus without complications.",
                    is_primary=True,
                    created_by=ugmc_doc,
                )
                Prescription.objects.create(
                    encounter=enc4,
                    drug_name="Metformin 500mg",
                    dosage="500mg oral",
                    frequency="Twice daily with meals",
                    created_by=ugmc_doc,
                )
                LabResult.objects.create(
                    encounter=enc4,
                    test_name="HbA1c",
                    result_value="7.2%",
                    reference_range="< 7.0%",
                    is_abnormal=True,
                    created_by=ugmc_nurse,
                )
                self.stdout.write(
                    "  + Created Cross-hospital Encounter: Emmanuel (TRUST patient) @ UGMC"
                )

            self.stdout.write(
                f"  {encounters_created} encounter(s) created (includes cross-hospital scenarios)."
            )

        # ── 5. Patient alerts / allergies (cross-hospital demo narrative) ────
        # Yaw has a severe penicillin allergy recorded at UGMC.
        # When a KATH doctor opens his record, the allergy strip appears in the
        # banner - demonstrating the value of the shared central record for
        # patient safety.
        if patient_list:
            patient_yaw = patient_list[0]
            ugmc_doc = user_map["ugmc_doctor"]
            ugmc_h = hospital_map["UGMC"]

            existing_allergy = PatientAlert.objects.filter(
                patient=patient_yaw,
                kind="ALLERGY",
                recorded_at_hospital=ugmc_h,
                is_active=True,
            ).first()

            if not existing_allergy:
                PatientAlert.objects.create(
                    patient=patient_yaw,
                    kind="ALLERGY",
                    label="Penicillin",
                    severity="SEVERE",
                    reaction="Anaphylaxis - bronchospasm and urticaria on previous exposure.",
                    recorded_by=ugmc_doc,
                    recorded_at_hospital=ugmc_h,
                    is_active=True,
                )
                self.stdout.write(
                    "  + Created Allergy: Yaw Mensah - Penicillin (SEVERE) @ UGMC\n"
                    "    -> Log in as 'kath_doctor' and open Yaw's record to see\n"
                    "      the cross-hospital allergy alert in the patient banner."
                )
            else:
                self.stdout.write("  Exists   Allergy: Yaw Mensah - Penicillin (SEVERE) @ UGMC")

        # ── 6. Phase B - Wards, Beds, Vitals, Appointments, Referrals ───────
        self._seed_phase_b(hospital_map, user_map, patient_list)

        # ── 7. Rich data - spread across all roles and hospitals ──────────
        self._seed_rich_data(hospital_map, user_map, patient_list)

        # ── Summary ───────────────────────────────────────────────────────
        self.stdout.write("\n" + self.style.SUCCESS("=== Demo data ready! ===\n"))
        self.stdout.write("Demo login credentials (password for all: Demo@123456)\n")
        self.stdout.write("-" * 52)
        self.stdout.write(f"{'Username':<20} {'Role':<20} {'Hospital'}")
        self.stdout.write("-" * 52)
        for username, _first, _last, role, hosp_code in STAFF:
            self.stdout.write(f"{username:<20} {role:<20} {hosp_code or 'N/A'}")
        self.stdout.write("-" * 52)
        self.stdout.write("Cross-hospital demo: log in as 'ugmc_doctor' and view")
        self.stdout.write("patient 'Yaw Mensah' - he has an encounter at KATH.")
        self.stdout.write("Then check the Audit Log as 'admin' to see the cross-hospital flag.\n")

    # ──────────────────────────────────────────────────────────────────────────
    def _seed_phase_b(self, hospital_map, user_map, patient_list):
        """Seed wards, beds, appointments, vitals, and referrals for Phase B demo."""
        from django.utils import timezone

        from hospitals.models import Bed, Ward
        from records.models import VitalSign
        from referrals.models import Referral
        from scheduling.models import Appointment

        ugmc = hospital_map["UGMC"]
        kath = hospital_map["KATH"]
        ugmc_nurse = user_map["ugmc_nurse"]
        ugmc_doctor = user_map["ugmc_doctor"]
        kath_doctor = user_map["kath_doctor"]
        ugmc_recept = user_map["ugmc_reception"]

        # ── Wards ─────────────────────────────────────────────────────────
        ward_a, _ = Ward.objects.get_or_create(
            hospital=ugmc,
            code="W3A",
            defaults={"name": "Ward 3A – General Medicine", "capacity": 24},
        )
        ward_icu, _ = Ward.objects.get_or_create(
            hospital=ugmc,
            code="ICU",
            defaults={"name": "Intensive Care Unit", "capacity": 8},
        )
        kath_ward, _ = Ward.objects.get_or_create(
            hospital=kath,
            code="CARD",
            defaults={"name": "Cardiology Ward", "capacity": 20},
        )

        # ── Beds ──────────────────────────────────────────────────────────
        for label, status in [
            ("A1", "occupied"),
            ("A2", "available"),
            ("A3", "cleaning"),
            ("B1", "occupied"),
            ("B2", "available"),
        ]:
            Bed.objects.get_or_create(ward=ward_a, label=label, defaults={"status": status})
        for label in ["ICU-1", "ICU-2", "ICU-3"]:
            Bed.objects.get_or_create(ward=ward_icu, label=label, defaults={"status": "available"})
        for label in ["C1", "C2", "C3"]:
            Bed.objects.get_or_create(ward=kath_ward, label=label, defaults={"status": "available"})

        self.stdout.write("  + Seeded wards and beds (UGMC W3A, ICU; KATH CARD)")

        # ── Vitals ────────────────────────────────────────────────────────
        if patient_list:
            patient_yaw = patient_list[0]
            if not VitalSign.objects.filter(patient=patient_yaw).exists():
                VitalSign.objects.create(
                    patient=patient_yaw,
                    recorded_by=ugmc_nurse,
                    recorded_at=timezone.now(),
                    temperature="37.8",
                    heart_rate=92,
                    respiratory_rate=18,
                    bp_systolic=138,
                    bp_diastolic=88,
                    spo2="97.5",
                    pain_score=4,
                    weight_kg="72.0",
                )
                self.stdout.write("  + Seeded vitals: Yaw Mensah")

        # ── Appointments ──────────────────────────────────────────────────
        if patient_list and len(patient_list) >= 2:
            patient_akosua = patient_list[1]
            tomorrow = timezone.now() + timezone.timedelta(days=1)
            _, created = Appointment.objects.get_or_create(
                patient=patient_akosua,
                hospital=kath,
                provider=kath_doctor,
                scheduled_for=tomorrow.replace(hour=9, minute=0, second=0, microsecond=0),
                defaults={
                    "appointment_type": "follow_up",
                    "status": "scheduled",
                    "reason": "Hypertension 3-month follow-up",
                    "created_by": ugmc_recept,
                },
            )
            if created:
                self.stdout.write("  + Seeded appointment: Akosua @ KATH (tomorrow 09:00)")

        # ── Referral ──────────────────────────────────────────────────────
        if patient_list:
            patient_yaw = patient_list[0]
            _, created = Referral.objects.get_or_create(
                patient=patient_yaw,
                from_hospital=ugmc,
                to_hospital=kath,
                from_provider=ugmc_doctor,
                defaults={
                    "reason": "Suspected acute MI - requires cardiology assessment at KATH.",
                    "priority": "stat",
                    "status": "sent",
                },
            )
            if created:
                self.stdout.write("  + Seeded referral: Yaw Mensah UGMC -> KATH (STAT, cardiology)")

    # ──────────────────────────────────────────────────────────────────────────
    def _seed_rich_data(self, hospital_map, user_map, patient_list):
        """
        Spread demo data across every role and hospital so that each dashboard
        shows non-zero metrics.  Covers:
          - TRUST ward/beds
          - Additional encounters (trust_doctor) back-dated over 14 days
          - LabOrders for each hospital
          - LabResults owned by each lab technician (ugmc_lab, kath_lab, trust_lab)
          - Cross-hospital AuditLog entries (via log_action)
          - Additional referrals (accepted + rejected)
          - Today's appointments (for receptionist dashboard)
          - MedicationAdministration entries (for nurse dashboard)
          - Additional VitalSign readings per nurse
          - Patient alert at KATH
        """
        from datetime import timedelta

        from django.utils import timezone

        from audit.utils import log_action
        from hospitals.models import Bed, Ward
        from patients.models import PatientAlert
        from records.models import (
            Diagnosis,
            Encounter,
            LabOrder,
            LabResult,
            MedicationAdministration,
            Prescription,
            VitalSign,
        )
        from referrals.models import Referral
        from scheduling.models import Appointment

        now = timezone.now()

        ugmc = hospital_map["UGMC"]
        kath = hospital_map["KATH"]
        trust = hospital_map["TRUST"]

        ugmc_doc = user_map["ugmc_doctor"]
        kath_doc = user_map["kath_doctor"]
        trust_doc = user_map["trust_doctor"]
        ugmc_nurse = user_map["ugmc_nurse"]
        kath_nurse = user_map["kath_nurse"]
        trust_nurse = user_map["trust_nurse"]
        ugmc_lab = user_map["ugmc_lab"]
        kath_lab = user_map["kath_lab"]
        trust_lab = user_map["trust_lab"]
        ugmc_recept = user_map["ugmc_reception"]

        patient_yaw = patient_list[0]
        patient_akosua = patient_list[1]
        patient_emmanuel = patient_list[2]
        patient_abena = patient_list[3]
        patient_kwame = patient_list[4]

        self.stdout.write(self.style.MIGRATE_HEADING("\n=== Seeding rich role data ===\n"))

        # ── 1. TRUST ward and beds ────────────────────────────────────────
        trust_ward, _ = Ward.objects.get_or_create(
            hospital=trust,
            code="GEN",
            defaults={"name": "General Medicine Ward", "capacity": 20},
        )
        for label, status in [
            ("T1", "occupied"),
            ("T2", "occupied"),
            ("T3", "available"),
            ("T4", "occupied"),
            ("T5", "available"),
        ]:
            Bed.objects.get_or_create(ward=trust_ward, label=label, defaults={"status": status})
        self.stdout.write("  + TRUST ward and beds (3 occupied / 2 available)")

        # Ensure KATH beds have some occupied status
        kath_ward = Ward.objects.filter(hospital=kath).first()
        if kath_ward:
            for label, status in [("C1", "occupied"), ("C2", "occupied"), ("C3", "available")]:
                bed, _ = Bed.objects.get_or_create(
                    ward=kath_ward, label=label, defaults={"status": status}
                )
                # Update existing beds to correct status if already created
                if bed.status != status:
                    Bed.objects.filter(pk=bed.pk).update(status=status)

        # ── 2. Additional encounters spread across doctors ────────────────
        def _make_enc(patient, doctor, hospital, etype, complaint, notes=""):
            enc, created = Encounter.objects.get_or_create(
                patient=patient,
                created_by=doctor,
                created_at_hospital=hospital,
                encounter_type=etype,
                defaults={"chief_complaint": complaint, "notes": notes},
            )
            return enc, created

        # trust_doctor: Emmanuel at TRUST (home hospital)
        enc5, c5 = _make_enc(
            patient_emmanuel,
            trust_doc,
            trust,
            "OPD",
            "Routine diabetes review - blood sugars elevated this month.",
            "Weight stable. FBS 10.2 mmol/L. HbA1c ordered.",
        )
        if c5:
            Diagnosis.objects.create(
                encounter=enc5,
                icd_code="E11.9",
                description="Type 2 diabetes mellitus - suboptimal glycaemic control.",
                is_primary=True,
                created_by=trust_doc,
            )
            self.stdout.write("  + Encounter: Emmanuel @ TRUST (trust_doctor)")

        # trust_doctor: Kwame at TRUST (cross-hospital - Kwame is UGMC patient)
        enc6, c6 = _make_enc(
            patient_kwame,
            trust_doc,
            trust,
            "FU",
            "Hypertension follow-up. Patient transferred from UGMC.",
            "BP 136/88 - Amlodipine dose increased to 10mg.",
        )
        if c6:
            Diagnosis.objects.create(
                encounter=enc6,
                icd_code="I10",
                description="Essential hypertension - partially controlled.",
                is_primary=True,
                created_by=trust_doc,
            )
            Prescription.objects.create(
                encounter=enc6,
                drug_name="Amlodipine 10mg",
                dosage="10mg oral",
                frequency="Once daily",
                created_by=trust_doc,
            )
            self.stdout.write("  + Encounter: Kwame @ TRUST (trust_doctor, cross-hospital)")

        # ugmc_doctor: Kwame at UGMC (home hospital, additional visit)
        enc7, c7 = _make_enc(
            patient_kwame,
            ugmc_doc,
            ugmc,
            "OPD",
            "Lower back pain for 2 weeks - no radiation to legs.",
            "Paraspinal tenderness. Musculoskeletal. X-ray ordered.",
        )
        if c7:
            Diagnosis.objects.create(
                encounter=enc7,
                icd_code="M54.5",
                description="Low back pain - mechanical, no neurological deficit.",
                is_primary=True,
                created_by=ugmc_doc,
            )
            self.stdout.write("  + Encounter: Kwame @ UGMC (ugmc_doctor)")

        # kath_doctor: Abena at KATH (home hospital)
        enc8, c8 = _make_enc(
            patient_abena,
            kath_doc,
            kath,
            "OPD",
            "Easy fatiguability and pallor for 3 months.",
            "Pallor ++. Icterus absent. Suspected iron-deficiency anaemia.",
        )
        if c8:
            Diagnosis.objects.create(
                encounter=enc8,
                icd_code="D50.9",
                description="Iron deficiency anaemia, unspecified.",
                is_primary=True,
                created_by=kath_doc,
            )
            Prescription.objects.create(
                encounter=enc8,
                drug_name="Ferrous Sulphate 200mg",
                dosage="200mg oral",
                frequency="Twice daily with food",
                created_by=kath_doc,
            )
            self.stdout.write("  + Encounter: Abena @ KATH (kath_doctor)")

        # ── 3. Back-date encounters for realistic 14-day trend lines ─────
        # auto_now_add prevents direct assignment; use .update() to bypass.
        backdate_map = [
            # (filter kwargs, days_ago)
            ({"patient": patient_yaw, "created_at_hospital": ugmc, "encounter_type": "OPD"}, 2),
            ({"patient": patient_akosua, "created_at_hospital": kath, "encounter_type": "FU"}, 5),
            ({"patient": patient_yaw, "created_at_hospital": kath, "encounter_type": "EMRG"}, 1),
            (
                {"patient": patient_emmanuel, "created_at_hospital": ugmc, "encounter_type": "OPD"},
                8,
            ),
            (
                {
                    "patient": patient_emmanuel,
                    "created_at_hospital": trust,
                    "encounter_type": "OPD",
                },
                7,
            ),
            ({"patient": patient_kwame, "created_at_hospital": trust, "encounter_type": "FU"}, 11),
            ({"patient": patient_kwame, "created_at_hospital": ugmc, "encounter_type": "OPD"}, 3),
            ({"patient": patient_abena, "created_at_hospital": kath, "encounter_type": "OPD"}, 5),
        ]
        for filt, days_ago in backdate_map:
            updated = Encounter.objects.filter(**filt).update(
                created_at=now - timedelta(days=days_ago)
            )
            if updated:
                self.stdout.write(
                    f"  + Back-dated {filt['encounter_type']} for {filt['patient'].universal_id} -> -{days_ago}d"
                )

        # ── 4. LabOrders ─────────────────────────────────────────────────
        # Re-fetch encounters by DB lookup (enc objects above may be fresh/stale)
        _enc1 = Encounter.objects.filter(
            patient=patient_yaw, created_at_hospital=ugmc, encounter_type="OPD"
        ).first()
        _enc2 = Encounter.objects.filter(
            patient=patient_akosua, created_at_hospital=kath, encounter_type="FU"
        ).first()
        _enc3 = Encounter.objects.filter(
            patient=patient_yaw, created_at_hospital=kath, encounter_type="EMRG"
        ).first()
        _enc5 = Encounter.objects.filter(
            patient=patient_emmanuel, created_at_hospital=trust, encounter_type="OPD"
        ).first()
        _enc7 = Encounter.objects.filter(
            patient=patient_kwame, created_at_hospital=ugmc, encounter_type="OPD"
        ).first()
        _enc8 = Encounter.objects.filter(
            patient=patient_abena, created_at_hospital=kath, encounter_type="OPD"
        ).first()

        orders_created = {}
        lab_order_specs = [
            # (key, patient, encounter, ordered_by, test_name, loinc, priority, status)
            (
                "o1",
                patient_yaw,
                _enc1,
                ugmc_doc,
                "Complete Blood Count",
                "58410-2",
                "stat",
                "resulted",
            ),
            ("o2", patient_kwame, _enc7, ugmc_doc, "HbA1c", "4548-4", "routine", "pending"),
            (
                "o3",
                patient_akosua,
                _enc2,
                kath_doc,
                "Liver Function Tests",
                "24325-3",
                "urgent",
                "in_progress",
            ),
            (
                "o4",
                patient_abena,
                _enc8,
                kath_doc,
                "Full Blood Count",
                "58410-2",
                "routine",
                "pending",
            ),
            (
                "o5",
                patient_emmanuel,
                _enc5,
                trust_doc,
                "Renal Function Tests",
                "24362-6",
                "routine",
                "resulted",
            ),
            (
                "o6",
                patient_yaw,
                _enc3,
                kath_doc,
                "Blood Culture & Sensitivity",
                "600-7",
                "urgent",
                "pending",
            ),
        ]
        for (
            key,
            patient,
            encounter,
            ordered_by,
            test_name,
            loinc,
            priority,
            status,
        ) in lab_order_specs:
            if not encounter:
                continue
            order, created = LabOrder.objects.get_or_create(
                patient=patient,
                encounter=encounter,
                test_name=test_name,
                defaults={
                    "ordered_by": ordered_by,
                    "loinc_code": loinc,
                    "priority": priority,
                    "status": status,
                },
            )
            orders_created[key] = order
            if created:
                self.stdout.write(
                    f"  + LabOrder: {test_name} for {patient.universal_id} ({priority}/{status})"
                )

        # ── 5. LabResults per lab technician ─────────────────────────────
        # Each (encounter, lab_user) pair has an expected count; only create
        # missing rows so the seed stays idempotent.
        lab_result_groups = [
            # (encounter, lab_user, [(test_name, result_value, reference_range, is_abnormal)])
            (
                _enc1,
                ugmc_lab,
                [
                    ("CBC - Haemoglobin", "11.2 g/dL (low)", "13.5–17.5 g/dL (M)", True),
                    ("Malaria RDT Repeat", "Negative", None, False),
                ],
            ),
            (
                _enc7,
                ugmc_lab,
                [
                    ("Random Blood Glucose", "5.4 mmol/L (normal)", "3.9–7.8 mmol/L", False),
                ],
            ),
            (
                _enc8,
                kath_lab,
                [
                    ("FBC - Haemoglobin", "8.5 g/dL (severe anaemia)", "11.5–16.5 g/dL (F)", True),
                ],
            ),
            (
                _enc2,
                kath_lab,
                [
                    ("LFT - ALT", "28 U/L (normal)", "7–40 U/L", False),
                ],
            ),
            (
                _enc5,
                trust_lab,
                [
                    (
                        "Urea & Creatinine",
                        "Creatinine 110 µmol/L (elevated)",
                        "62–106 µmol/L",
                        True,
                    ),
                    (
                        "Urinalysis",
                        "Protein: trace; Glucose: negative; Ketones: negative",
                        None,
                        False,
                    ),
                ],
            ),
        ]
        for encounter, lab_user, results in lab_result_groups:
            if not encounter:
                continue
            existing_count = LabResult.objects.filter(
                encounter=encounter, created_by=lab_user
            ).count()
            for test_name, result_value, reference_range, is_abnormal in results[existing_count:]:
                kwargs = {
                    "encounter": encounter,
                    "test_name": test_name,
                    "result_value": result_value,
                    "is_abnormal": is_abnormal,
                    "created_by": lab_user,
                }
                if reference_range:
                    kwargs["reference_range"] = reference_range
                LabResult.objects.create(**kwargs)
                self.stdout.write(
                    f"  + LabResult: {test_name} "
                    f"({'abnormal' if is_abnormal else 'normal'}) by {lab_user.username}"
                )

        # ── 6. Cross-hospital AuditLog entries ───────────────────────────
        # log_action uses the advisory lock + hash chain - safe to call here.
        class _MockRequest:
            """Thin mock so log_action can extract user + IP from a command."""

            def __init__(self, user):
                self.user = user
                self.META = {
                    "REMOTE_ADDR": "127.0.0.1",
                    "HTTP_USER_AGENT": "seed_demo/management_command",
                }

        from audit.models import AuditLog

        cross_audit_specs = [
            # (actor, action, patient, is_cross)
            (kath_doc, "VIEW_PATIENT", patient_yaw, True),
            (ugmc_doc, "VIEW_PATIENT", patient_emmanuel, True),
            (trust_doc, "VIEW_PATIENT", patient_yaw, True),
            (kath_doc, "CREATE_ENCOUNTER", patient_yaw, True),
            (ugmc_doc, "CREATE_ENCOUNTER", patient_emmanuel, True),
        ]
        for actor, action, patient, is_cross in cross_audit_specs:
            already = AuditLog.objects.filter(
                actor=actor,
                action=action,
                patient_nhid=patient.universal_id,
            ).exists()
            if not already:
                log_action(
                    _MockRequest(actor),
                    action,
                    target=patient,
                    patient=patient,
                    is_cross_hospital=is_cross,
                )
                self.stdout.write(
                    f"  + Audit: {actor.username} -> {action} -> {patient.universal_id}"
                )

        # ── 7. Additional referrals (accepted + rejected) ─────────────────
        referral_specs = [
            # (patient, from_h, to_h, from_doc, reason, priority, status, status_notes)
            (
                patient_akosua,
                kath,
                ugmc,
                kath_doc,
                "Recurrent hypertensive urgency - cardiology opinion required at UGMC.",
                "urgent",
                "accepted",
                "UGMC Cardiology confirmed an available slot within 48 hours.",
            ),
            (
                patient_emmanuel,
                trust,
                kath,
                trust_doc,
                "Diabetic nephropathy - nephrology review requested at KATH.",
                "routine",
                "rejected",
                "KATH Nephrology at full capacity; review requested again in 3 months.",
            ),
        ]
        for patient, from_h, to_h, from_doc, reason, priority, status, notes in referral_specs:
            _, created = Referral.objects.get_or_create(
                patient=patient,
                from_hospital=from_h,
                to_hospital=to_h,
                from_provider=from_doc,
                defaults={
                    "reason": reason,
                    "priority": priority,
                    "status": status,
                    "status_notes": notes,
                },
            )
            if created:
                self.stdout.write(
                    f"  + Referral: {patient.universal_id} {from_h.code}->{to_h.code} ({status})"
                )

        # ── 8. Today's appointments (receptionist dashboard) ──────────────
        t9 = now.replace(hour=9, minute=0, second=0, microsecond=0)
        t10 = now.replace(hour=10, minute=0, second=0, microsecond=0)
        t11 = now.replace(hour=11, minute=0, second=0, microsecond=0)
        t14 = now.replace(hour=14, minute=0, second=0, microsecond=0)

        appt_specs = [
            # (patient, hospital, provider, scheduled_for, appt_type, status, reason)
            (patient_yaw, ugmc, ugmc_doc, t9, "outpatient", "checked_in", "Malaria follow-up"),
            (patient_kwame, ugmc, ugmc_doc, t10, "follow_up", "scheduled", "Back pain review"),
            (patient_emmanuel, ugmc, ugmc_doc, t11, "outpatient", "no_show", "Diabetes check-up"),
            (patient_akosua, kath, kath_doc, t9, "follow_up", "checked_in", "Hypertension review"),
            (patient_abena, kath, kath_doc, t10, "outpatient", "scheduled", "Anaemia workup"),
            (
                patient_emmanuel,
                trust,
                trust_doc,
                t14,
                "follow_up",
                "scheduled",
                "Diabetes management",
            ),
        ]
        for patient, hospital, provider, scheduled_for, appt_type, status, reason in appt_specs:
            _, created = Appointment.objects.get_or_create(
                patient=patient,
                hospital=hospital,
                provider=provider,
                scheduled_for=scheduled_for,
                defaults={
                    "appointment_type": appt_type,
                    "status": status,
                    "reason": reason,
                    "created_by": ugmc_recept,
                    "duration_minutes": 30,
                },
            )
            if created:
                self.stdout.write(
                    f"  + Appointment: {patient.universal_id} @ {hospital.code} "
                    f"{scheduled_for.strftime('%H:%M')} ({status})"
                )

        # ── 9. MedicationAdministration (nurse dashboard) ──────────────────
        # Create "given" (yesterday) + "due" (today) dose records per prescription.
        nurse_by_hosp = {ugmc: ugmc_nurse, kath: kath_nurse, trust: trust_nurse}
        prescriptions = (
            Prescription.objects.filter(encounter__created_at_hospital__in=[ugmc, kath, trust])
            .select_related("encounter__created_at_hospital")
            .order_by("created_at")[:10]
        )
        for i, rx in enumerate(prescriptions):
            if rx.administrations.exists():
                continue
            hosp = rx.encounter.created_at_hospital
            nurse = nurse_by_hosp.get(hosp)
            if not nurse:
                continue
            yesterday_8am = (now - timedelta(days=1)).replace(
                hour=8, minute=0, second=0, microsecond=0
            )
            today_8am = now.replace(hour=8, minute=0, second=0, microsecond=0)
            # Yesterday's dose - always given
            MedicationAdministration.objects.create(
                prescription=rx,
                administered_by=nurse,
                scheduled_time=yesterday_8am,
                administered_time=yesterday_8am.replace(minute=15),
                status="given",
            )
            # Today's dose - rotate through due / given / missed
            status_today = ["due", "given", "missed"][i % 3]
            MedicationAdministration.objects.create(
                prescription=rx,
                administered_by=nurse,
                scheduled_time=today_8am,
                administered_time=today_8am.replace(minute=30) if status_today == "given" else None,
                status=status_today,
            )
            self.stdout.write(
                f"  + MedAdmin: {rx.drug_name} by {nurse.username} (today: {status_today})"
            )

        # ── 10. Additional VitalSigns ──────────────────────────────────────
        vitals_specs = [
            # (patient, nurse, temp, hr, rr, sbp, dbp, spo2, weight_kg)
            (patient_akosua, kath_nurse, "37.2", 78, 16, 130, 85, "98.5", "63.0"),
            (patient_abena, kath_nurse, "36.6", 95, 18, 110, 70, "98.0", "52.0"),
            (patient_emmanuel, trust_nurse, "37.0", 82, 16, 142, 92, "97.0", "85.5"),
            (patient_kwame, ugmc_nurse, "36.8", 70, 14, 118, 76, "99.0", "75.0"),
        ]
        for patient, nurse, temp, hr, rr, sbp, dbp, spo2, weight in vitals_specs:
            if VitalSign.objects.filter(patient=patient, recorded_by=nurse).exists():
                continue
            VitalSign.objects.create(
                patient=patient,
                recorded_by=nurse,
                recorded_at=now,
                temperature=temp,
                heart_rate=hr,
                respiratory_rate=rr,
                bp_systolic=sbp,
                bp_diastolic=dbp,
                spo2=spo2,
                weight_kg=weight,
            )
            self.stdout.write(f"  + VitalSign: {patient.universal_id} by {nurse.username}")

        # ── 11. Patient alert at KATH (Abena - latex allergy) ──────────────
        if not PatientAlert.objects.filter(patient=patient_abena, kind="ALLERGY").exists():
            PatientAlert.objects.create(
                patient=patient_abena,
                kind="ALLERGY",
                label="Latex",
                severity="MODERATE",
                reaction="Contact dermatitis and urticaria on latex glove exposure.",
                recorded_by=kath_doc,
                recorded_at_hospital=kath,
                is_active=True,
            )
            self.stdout.write("  + Alert: Abena Asante - Latex allergy (MODERATE) @ KATH")

        self.stdout.write(self.style.SUCCESS("\n  + Rich role data seeded successfully.\n"))
