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
