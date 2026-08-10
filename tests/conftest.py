"""
Shared pytest fixtures for the EMR test suite.

Factories build the minimum necessary objects for each test; they do NOT
use the seed_demo command (which is for demo data, not testing).
"""

import pytest
from django.contrib.auth import get_user_model

User = get_user_model()


# ── Hospitals ──────────────────────────────────────────────────────────────


@pytest.fixture
def hospital_a(db):
    from hospitals.models import Hospital

    return Hospital.objects.create(name="Hospital A", code="HSPA", city="Accra")


@pytest.fixture
def hospital_b(db):
    from hospitals.models import Hospital

    return Hospital.objects.create(name="Hospital B", code="HSPB", city="Kumasi")


# ── Users ──────────────────────────────────────────────────────────────────


def _make_user(username, role, hospital=None, password="Test@password1"):
    user = User.objects.create_user(
        username=username,
        password=password,
        role=role,
        hospital=hospital,
        first_name=username.capitalize(),
        last_name="Demo",
        email=f"{username}@test.local",
    )
    return user


@pytest.fixture
def doctor_a(db, hospital_a):
    return _make_user("doctor_a", "doctor", hospital_a)


@pytest.fixture
def nurse_a(db, hospital_a):
    return _make_user("nurse_a", "nurse", hospital_a)


@pytest.fixture
def doctor_b(db, hospital_b):
    return _make_user("doctor_b", "doctor", hospital_b)


@pytest.fixture
def receptionist_a(db, hospital_a):
    return _make_user("recept_a", "receptionist", hospital_a)


@pytest.fixture
def sys_admin(db):
    return _make_user("sysadmin", "super_admin")


# ── Patients ───────────────────────────────────────────────────────────────


@pytest.fixture
def patient_a(db, hospital_a, doctor_a):
    """Patient registered at Hospital A."""
    from patients.models import Patient

    return Patient.objects.create(
        first_name="Yaw",
        last_name="Mensah",
        date_of_birth="1985-03-12",
        sex="M",
        blood_group="A+",
        national_id="GHA-TEST-001",
        registered_at_hospital=hospital_a,
        registered_by=doctor_a,
    )


@pytest.fixture
def patient_b(db, hospital_b, doctor_b):
    """Patient registered at Hospital B."""
    from patients.models import Patient

    return Patient.objects.create(
        first_name="Akosua",
        last_name="Owusu",
        date_of_birth="1992-07-24",
        sex="F",
        blood_group="O+",
        national_id="GHA-TEST-002",
        registered_at_hospital=hospital_b,
        registered_by=doctor_b,
    )


# ── Encounters ─────────────────────────────────────────────────────────────


@pytest.fixture
def encounter_a(db, patient_a, doctor_a, hospital_a):
    """An encounter created at Hospital A."""
    from records.models import Encounter

    return Encounter.objects.create(
        patient=patient_a,
        encounter_type="OPD",
        chief_complaint="Fever and headache",
        notes="Temp 38.5°C",
        created_by=doctor_a,
        created_at_hospital=hospital_a,
    )


# ── Django test client helpers ─────────────────────────────────────────────


@pytest.fixture
def client_as_doctor_a(client, doctor_a):
    """Authenticated test client logged in as doctor_a."""
    client.force_login(doctor_a)
    return client


@pytest.fixture
def client_as_doctor_b(client, doctor_b):
    client.force_login(doctor_b)
    return client


@pytest.fixture
def client_as_receptionist(client, receptionist_a):
    client.force_login(receptionist_a)
    return client


@pytest.fixture
def client_as_sysadmin(client, sys_admin):
    client.force_login(sys_admin)
    return client
