"""
Tests for field-level encryption (core/fields.py) and blind index (core/blind_index.py).

Verifies:
  - Fernet round-trip: encrypt → store → read → plaintext recovered
  - Database column stores ciphertext, not plaintext
  - Wrong key returns '[decryption error]' gracefully
  - Blind-index is deterministic, keyed, returns empty string for empty input
"""

from django.test import override_settings

# ── Encryption round-trip ──────────────────────────────────────────────────


class TestEncryptDecrypt:
    def test_encrypt_decrypt_roundtrip(self):
        from core.fields import decrypt_value, encrypt_value

        plaintext = "Kwame Asante"
        ciphertext = encrypt_value(plaintext)
        assert ciphertext != plaintext, "Ciphertext must not equal plaintext"
        assert ciphertext.startswith("gAAAAA"), "Fernet tokens start with gAAAAA"
        assert decrypt_value(ciphertext) == plaintext

    def test_ciphertext_is_not_plaintext(self, db, patient_a):
        """The database column must contain ciphertext, not plaintext."""
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT first_name FROM patients_patient WHERE id = %s",
                [patient_a.pk],
            )
            raw = cursor.fetchone()[0]
        assert raw.startswith("gAAAAA"), (
            f"DB column should contain Fernet ciphertext; got: {raw[:20]!r}"
        )
        assert "Yaw" not in raw, "Plaintext should NOT appear in DB column"

    def test_decrypt_with_wrong_key_returns_placeholder(self):
        from core.fields import _clear_fernet_cache, decrypt_value, encrypt_value

        ciphertext = encrypt_value("sensitive data")
        _clear_fernet_cache()
        with override_settings(
            FIELD_ENCRYPTION_KEYS="",
            FIELD_ENCRYPTION_KEY="d2Fyb25nLWtleS13YXJvbmcta2V5LXdhcm9uZy1rZXk=",
        ):
            result = decrypt_value(ciphertext)
        _clear_fernet_cache()
        assert result == "[decryption error]"

    def test_multi_key_rotation(self):
        """
        Data encrypted with key A can be decrypted after rotation when key B
        is primary and key A is secondary (FIELD_ENCRYPTION_KEYS=keyB,keyA).
        """
        from cryptography.fernet import Fernet

        from core.fields import _clear_fernet_cache, decrypt_value, encrypt_value

        key_a = Fernet.generate_key().decode()
        key_b = Fernet.generate_key().decode()

        # Step 1: Encrypt with Key A as sole key
        _clear_fernet_cache()
        with override_settings(FIELD_ENCRYPTION_KEYS=key_a, FIELD_ENCRYPTION_KEY=""):
            ciphertext = encrypt_value("Data to rotate")
        _clear_fernet_cache()

        # Step 2: Rotate — Key B is primary (new writes), Key A is secondary
        with override_settings(
            FIELD_ENCRYPTION_KEYS=f"{key_b},{key_a}",
            FIELD_ENCRYPTION_KEY="",
        ):
            decrypted = decrypt_value(ciphertext)
        _clear_fernet_cache()

        assert decrypted == "Data to rotate", "Must decrypt data encrypted with secondary key"

    def test_gAAAAA_prefixed_plaintext_survives_round_trip(self, db):
        """
        Regression for M1: a legitimate plaintext value that begins with 'gAAAAA'
        (which looks like a Fernet token prefix) must be stored encrypted and
        recovered correctly.  The old heuristic in get_prep_value would skip
        encryption and store it verbatim, causing a later decrypt failure.
        """
        from patients.models import Patient

        # 'gAAAAA' is the standard Fernet token prefix; a free-text value could
        # legitimately start with these characters (e.g. an address or note).
        edge_case_address = "gAAAAA Dangerous Prefix Avenue, Accra"
        p = Patient.objects.create(
            first_name="Edge",
            last_name="Case",
            date_of_birth="2000-01-01",
            address=edge_case_address,
        )

        # Verify it was stored as ciphertext (not as the raw prefix string)
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute("SELECT address FROM patients_patient WHERE id = %s", [p.pk])
            raw = cursor.fetchone()[0]
        assert raw.startswith("gAAAAA"), "address must be Fernet-encrypted in DB"
        # But the raw DB value must NOT be the literal plaintext
        assert raw != edge_case_address, "plaintext must not be stored verbatim"

        # Verify round-trip: reading back gives the original plaintext
        p_fresh = Patient.objects.get(pk=p.pk)
        assert p_fresh.address == edge_case_address

    def test_encrypted_field_on_model(self, db, patient_a):
        """Reading the model attribute returns the decrypted plaintext."""
        from patients.models import Patient

        p = Patient.objects.get(pk=patient_a.pk)
        assert p.first_name == "Yaw"
        assert p.last_name == "Mensah"


# ── Blind index ────────────────────────────────────────────────────────────


class TestBlindIndex:
    def test_deterministic(self):
        from core.blind_index import make_blind_index

        h1 = make_blind_index("Yaw Mensah")
        h2 = make_blind_index("Yaw Mensah")
        assert h1 == h2

    def test_case_insensitive(self):
        from core.blind_index import make_blind_index

        assert make_blind_index("YAW MENSAH") == make_blind_index("yaw mensah")

    def test_different_inputs_different_hashes(self):
        from core.blind_index import make_blind_index

        assert make_blind_index("Alice") != make_blind_index("Bob")

    def test_empty_input_returns_empty(self):
        from core.blind_index import make_blind_index

        assert make_blind_index("") == ""
        assert make_blind_index(None) == ""

    def test_hash_is_hex_64_chars(self):
        from core.blind_index import make_blind_index

        h = make_blind_index("Test Patient")
        assert len(h) == 64
        int(h, 16)  # must be valid hex

    def test_blind_index_stored_on_patient(self, db, patient_a):
        """Patient.name_hash and national_id_hash are populated on save."""
        from core.blind_index import make_blind_index
        from patients.models import Patient

        p = Patient.objects.get(pk=patient_a.pk)
        expected_name_hash = make_blind_index("Yaw Mensah")
        assert p.name_hash == expected_name_hash
        expected_nid_hash = make_blind_index("GHA-TEST-001")
        assert p.national_id_hash == expected_nid_hash

    def test_blind_index_key_required_in_production(self):
        import pytest
        from django.core.exceptions import ImproperlyConfigured

        from core.blind_index import _get_key

        with override_settings(DEBUG=False, BLIND_INDEX_KEY=""):
            with pytest.raises(ImproperlyConfigured, match="BLIND_INDEX_KEY must be set"):
                _get_key()

    def test_blind_index_key_cannot_equal_secret_key_in_production(self):
        import pytest
        from django.core.exceptions import ImproperlyConfigured

        from core.blind_index import _get_key

        with override_settings(
            DEBUG=False, BLIND_INDEX_KEY="shared-secret", SECRET_KEY="shared-secret"
        ):
            with pytest.raises(ImproperlyConfigured, match="cryptographic key isolation"):
                _get_key()

    def test_blind_index_key_fallback_in_debug(self, caplog):
        import logging

        from core.blind_index import _get_key

        with override_settings(DEBUG=True, BLIND_INDEX_KEY="", SECRET_KEY="dev-secret-key"):
            with caplog.at_level(logging.WARNING):
                key = _get_key()
                assert key == b"dev-secret-key"
                assert "BLIND_INDEX_KEY is unset or identical to SECRET_KEY" in caplog.text


# ── Clinical Code Encryption & Blind Indexing ─────────────────────────────


class TestClinicalCodeEncryption:
    """
    Verify that clinical/diagnostic codes (ICD-10, SNOMED, RxNorm, LOINC) and lab
    order test names are encrypted with Fernet in the database and indexed via HMAC-SHA256
    blind indexes for exact matching (Act 843 Part V §32 compliance).
    """

    def test_diagnosis_codes_encrypted_in_db_and_blind_indexed(self, db, encounter_a):
        from django.db import connection

        from core.blind_index import make_blind_index
        from records.models import Diagnosis

        diag = Diagnosis.objects.create(
            encounter=encounter_a,
            icd_code="B20",
            snomed_code="86406008",
            description="Human immunodeficiency virus disease",
            is_primary=True,
        )

        # 1. Verify DB contains raw ciphertext, NOT plaintext
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT icd_code, snomed_code, icd_code_hash, snomed_code_hash FROM records_diagnosis WHERE id = %s",
                [diag.pk],
            )
            raw_icd, raw_snomed, raw_icd_hash, raw_snomed_hash = cursor.fetchone()

        assert raw_icd.startswith("gAAAAA"), "icd_code must be Fernet-encrypted in DB"
        assert raw_snomed.startswith("gAAAAA"), "snomed_code must be Fernet-encrypted in DB"
        assert "B20" not in raw_icd, "icd_code plaintext must not appear in DB column"
        assert "86406008" not in raw_snomed, "snomed_code plaintext must not appear in DB column"

        # 2. Verify plain LIKE 'B20%' query finds 0 records (closing the Act 843 leak)
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM records_diagnosis WHERE icd_code LIKE 'B20%'")
            count = cursor.fetchone()[0]
        assert count == 0, "LIKE query on ciphertext must not leak diagnosed condition"

        # 3. Verify blind index hashes match expected HMAC digests
        expected_icd_hash = make_blind_index("B20")
        expected_snomed_hash = make_blind_index("86406008")
        assert raw_icd_hash == expected_icd_hash
        assert raw_snomed_hash == expected_snomed_hash

        # 4. Verify exact-match ORM lookup via blind index
        found = Diagnosis.objects.filter(icd_code_hash=expected_icd_hash).first()
        assert found is not None
        assert found.pk == diag.pk
        # 5. Verify transparent decryption on read
        assert found.icd_code == "B20"
        assert found.snomed_code == "86406008"

    def test_prescription_rxnorm_encrypted_and_blind_indexed(self, db, encounter_a):
        from django.db import connection

        from core.blind_index import make_blind_index
        from records.models import Prescription

        rx = Prescription.objects.create(
            encounter=encounter_a,
            drug_name="Dolutegravir",
            rxnorm_code="1433868",
            dosage="50mg daily",
            frequency="OD",
        )

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT rxnorm_code, rxnorm_code_hash FROM records_prescription WHERE id = %s",
                [rx.pk],
            )
            raw_rxnorm, raw_rxnorm_hash = cursor.fetchone()

        assert raw_rxnorm.startswith("gAAAAA")
        assert "1433868" not in raw_rxnorm
        assert raw_rxnorm_hash == make_blind_index("1433868")

        found = Prescription.objects.filter(rxnorm_code_hash=make_blind_index("1433868")).first()
        assert found is not None
        assert found.rxnorm_code == "1433868"

    def test_lab_order_and_result_codes_encrypted_and_blind_indexed(
        self, db, patient_a, encounter_a
    ):
        from django.db import connection

        from core.blind_index import make_blind_index
        from records.models import LabOrder, LabResult

        order = LabOrder.objects.create(
            patient=patient_a,
            encounter=encounter_a,
            test_name="HIV Viral Load",
            loinc_code="25836-8",
        )

        result = LabResult.objects.create(
            encounter=encounter_a,
            order=order,
            test_name="HIV Viral Load",
            loinc_code="25836-8",
            result_value="< 20 copies/mL",
        )

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT test_name, loinc_code, test_name_hash, loinc_code_hash FROM records_laborder WHERE id = %s",
                [order.pk],
            )
            lo_test, lo_loinc, lo_test_hash, lo_loinc_hash = cursor.fetchone()

            cursor.execute(
                "SELECT test_name, loinc_code, test_name_hash, loinc_code_hash FROM records_labresult WHERE id = %s",
                [result.pk],
            )
            lr_test, lr_loinc, lr_test_hash, lr_loinc_hash = cursor.fetchone()

        # LabOrder assertions
        assert lo_test.startswith("gAAAAA")
        assert lo_loinc.startswith("gAAAAA")
        assert lo_test_hash == make_blind_index("HIV Viral Load")
        assert lo_loinc_hash == make_blind_index("25836-8")

        # LabResult assertions
        assert lr_test.startswith("gAAAAA")
        assert lr_loinc.startswith("gAAAAA")
        assert lr_test_hash == make_blind_index("HIV Viral Load")
        assert lr_loinc_hash == make_blind_index("25836-8")

        # Searchability assertions
        assert (
            LabOrder.objects.filter(test_name_hash=make_blind_index("HIV Viral Load")).count() == 1
        )
        assert LabResult.objects.filter(loinc_code_hash=make_blind_index("25836-8")).count() == 1

        # Decryption assertions
        refetched_order = LabOrder.objects.get(pk=order.pk)
        assert refetched_order.test_name == "HIV Viral Load"
        assert refetched_order.loinc_code == "25836-8"

        refetched_result = LabResult.objects.get(pk=result.pk)
        assert refetched_result.test_name == "HIV Viral Load"
        assert refetched_result.loinc_code == "25836-8"
