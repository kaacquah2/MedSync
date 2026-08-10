"""
Tests for EMPI duplicate-detection logic (patients/empi.py).

Verifies all four confidence tiers:
  - no_match  — nothing in the DB
  - exact     — deterministic national-ID match (single result)
  - conflict  — two records with the same national-ID hash
  - probable  — name-only match
  - probable  — name + DOB match
  - no_match  — name matches but DOB does not
"""

import pytest


@pytest.fixture
def _patients(db, hospital_a, hospital_b, doctor_a, doctor_b):
    """Creates a pair of patients for EMPI testing."""
    from patients.models import Patient

    alice = Patient.objects.create(
        first_name="Alice",
        last_name="Mensah",
        date_of_birth="1990-05-15",
        sex="F",
        blood_group="B+",
        national_id="GHA-EMPI-ALICE",
        registered_at_hospital=hospital_a,
        registered_by=doctor_a,
    )
    bob = Patient.objects.create(
        first_name="Bob",
        last_name="Asante",
        date_of_birth="1975-11-02",
        sex="M",
        blood_group="O+",
        national_id="GHA-EMPI-BOB",
        registered_at_hospital=hospital_b,
        registered_by=doctor_b,
    )
    return alice, bob


class TestEMPINoMatch:
    def test_empty_db_returns_no_match(self, db):
        from patients.empi import match_patient

        result = match_patient(national_id="GHA-NOBODY", name="Ghost Patient", dob="2000-01-01")
        assert result.confidence == "no_match"
        assert result.candidates == []

    def test_name_match_wrong_dob_returns_no_match(self, _patients):
        from patients.empi import match_patient

        alice, _ = _patients
        result = match_patient(name="Alice Mensah", dob="1999-01-01")
        assert result.confidence == "no_match"


class TestEMPIExact:
    def test_national_id_returns_exact(self, _patients):
        from patients.empi import match_patient

        alice, _ = _patients
        result = match_patient(national_id="GHA-EMPI-ALICE")
        assert result.confidence == "exact"
        assert len(result.candidates) == 1
        assert result.candidates[0].pk == alice.pk

    def test_message_contains_nhid(self, _patients):
        from patients.empi import match_patient

        alice, _ = _patients
        result = match_patient(national_id="GHA-EMPI-ALICE")
        assert alice.universal_id in result.message


class TestEMPIConflict:
    def test_two_records_same_national_id_returns_conflict(
        self, db, hospital_a, hospital_b, doctor_a, doctor_b
    ):
        """
        Two patient records with identical national_id produce a conflict
        (the EMPI finds more than one deterministic match — data quality issue).
        """
        from patients.empi import match_patient
        from patients.models import Patient

        # Create two patients sharing the same national ID value
        Patient.objects.create(
            first_name="Twin",
            last_name="One",
            date_of_birth="1985-01-01",
            sex="M",
            national_id="GHA-DUPLICATE",
            registered_at_hospital=hospital_a,
            registered_by=doctor_a,
        )
        Patient.objects.create(
            first_name="Twin",
            last_name="Two",
            date_of_birth="1985-01-02",
            sex="M",
            national_id="GHA-DUPLICATE",
            registered_at_hospital=hospital_b,
            registered_by=doctor_b,
        )
        result = match_patient(national_id="GHA-DUPLICATE")
        assert result.confidence == "conflict"
        assert len(result.candidates) == 2


class TestEMPIProbable:
    def test_name_only_match_returns_probable(self, _patients):
        from patients.empi import match_patient

        alice, _ = _patients
        result = match_patient(name="Alice Mensah")
        assert result.confidence == "probable"
        assert any(c.pk == alice.pk for c in result.candidates)

    def test_name_and_dob_match_returns_probable(self, _patients):
        from patients.empi import match_patient

        alice, _ = _patients
        result = match_patient(name="Alice Mensah", dob="1990-05-15")
        assert result.confidence == "probable"
        assert any(c.pk == alice.pk for c in result.candidates)

    def test_name_case_insensitive(self, _patients):
        """Blind index normalises to lowercase — case should not matter."""
        from patients.empi import match_patient

        alice, _ = _patients
        result = match_patient(name="alice mensah")
        assert result.confidence == "probable"

    def test_no_name_no_national_id_returns_no_match(self, _patients):
        from patients.empi import match_patient

        result = match_patient(dob="1990-05-15")  # DOB alone is not indexed
        assert result.confidence == "no_match"
