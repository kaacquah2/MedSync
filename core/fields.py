"""
Field-level encryption using Fernet (symmetric AES-128-CBC + HMAC-SHA256).

Provides EncryptedCharField and EncryptedTextField — drop-in replacements for
their Django equivalents that transparently encrypt on save and decrypt on load.

Key configuration (in priority order):
  1. FIELD_ENCRYPTION_KEYS (comma-separated list) — enables key rotation.
     The FIRST key is used for encryption; ALL keys are tried for decryption.
     To rotate: prepend the new key, run `manage.py reencrypt_fields`, then
     remove the old key.  See docs/runbook.md for the full procedure.

  2. FIELD_ENCRYPTION_KEY (single key, legacy) — still supported for
     backwards compatibility.  Behaves identically to a one-element
     FIELD_ENCRYPTION_KEYS list.

  Generate a new key:
      python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

Security note:
  - Encrypted values are stored as text (base-64 ciphertext).
  - The column in the database contains NO plaintext, satisfying the
    "encryption at rest" requirement at the application layer.
  - Neon/Postgres also encrypts storage at rest by default (double layered).
  - Fernet guarantees authenticated encryption: tampering is detected.
  - Searching/filtering on encrypted fields is NOT supported (by design).
  - MultiFernet decrypts with the first matching key, so rolling rotation
    works without a re-encryption downtime window.
"""

import logging

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.db import models

logger = logging.getLogger(__name__)


_fernet_cache: "MultiFernet | None" = None


def _clear_fernet_cache() -> None:
    """Invalidate the cached MultiFernet instance. Used by tests and key-rotation commands."""
    global _fernet_cache
    _fernet_cache = None


def _build_fernet() -> MultiFernet:
    """
    Build a MultiFernet from settings.

    Reads FIELD_ENCRYPTION_KEYS (comma-separated, new key first) or falls
    back to the legacy FIELD_ENCRYPTION_KEY.  Always returns a MultiFernet
    (even with one key) so the API is uniform.
    """
    # Prefer the multi-key list (rotation-ready)
    multi_raw = getattr(settings, "FIELD_ENCRYPTION_KEYS", "")
    if multi_raw:
        key_strings = [k.strip() for k in multi_raw.split(",") if k.strip()]
    else:
        # Legacy single-key fallback
        single = getattr(settings, "FIELD_ENCRYPTION_KEY", "")
        if not single:
            raise ValueError(
                "Neither FIELD_ENCRYPTION_KEYS nor FIELD_ENCRYPTION_KEY is set. "
                'Generate a key with: python -c "from cryptography.fernet import '
                'Fernet; print(Fernet.generate_key().decode())"'
            )
        key_strings = [single]

    fernets = []
    for ks in key_strings:
        raw = ks.encode() if isinstance(ks, str) else ks
        fernets.append(Fernet(raw))

    return MultiFernet(fernets)


def _get_fernet() -> MultiFernet:
    """
    Return the cached MultiFernet instance, building it on first call.

    The instance is module-level-cached to avoid rebuilding on every field
    access (which would re-parse settings on every encrypt/decrypt call).
    Call _clear_fernet_cache() after key rotation to force a rebuild.
    """
    global _fernet_cache
    if _fernet_cache is None:
        _fernet_cache = _build_fernet()
    return _fernet_cache


def encrypt_value(plaintext: str) -> str:
    """Encrypt a unicode string using the primary (first) key."""
    return _get_fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_value(ciphertext: str) -> str:
    """
    Decrypt a base-64 ciphertext string.

    Tries all configured keys (MultiFernet).  Returns a safe placeholder
    on InvalidToken (wrong key / corrupted data) and logs unexpected errors
    rather than swallowing them silently.
    """
    if not ciphertext or not ciphertext.startswith("gAAAAA"):
        return ciphertext
    try:
        return _get_fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except InvalidToken:
        # Token cannot be decrypted by any configured key — wrong key or corruption.
        logger.warning(
            "Field decryption failed (InvalidToken) — check FIELD_ENCRYPTION_KEYS. "
            "If you rotated keys, run: manage.py reencrypt_fields"
        )
        return "[decryption error]"
    except Exception:
        logger.exception("Unexpected error decrypting field value")
        return "[decryption error]"


class EncryptedMixin:
    """Mixin that adds transparent encryption/decryption to a field."""

    def from_db_value(self, value, expression, connection):
        if value is None or value == "":
            return value
        return decrypt_value(value)

    def get_prep_value(self, value):
        if value is None or value == "":
            return value
        # Always encrypt on write.  from_db_value() decrypts on read, so the
        # attribute is always plaintext when this method is called in normal
        # Django usage.  The previous heuristic (skipping values that start
        # with "gAAAAA") was fragile: any legitimate PHI beginning with that
        # prefix would be stored unencrypted and later fail to decrypt.
        # Fernet produces unique ciphertext for each encrypt call, so
        # encrypting an already-decrypted plaintext is safe.
        return encrypt_value(str(value))

    def to_python(self, value):
        # Called during form validation — value arrives as plaintext from the form
        return value


class EncryptedCharField(EncryptedMixin, models.TextField):
    """
    Like CharField but stored encrypted.
    We back it with TextField in the DB to hold the larger ciphertext.
    Pass max_length to the constructor only for form validation; it is NOT
    applied at the DB level (the ciphertext is longer than the plaintext).
    """

    def __init__(self, *args, **kwargs):
        self._plaintext_max_length = kwargs.pop("max_length", None)
        # Do NOT pass max_length to TextField — it doesn't use it at the DB level
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        if self._plaintext_max_length is not None:
            kwargs["max_length"] = self._plaintext_max_length
        return name, path, args, kwargs


class EncryptedTextField(EncryptedMixin, models.TextField):
    """Like TextField but stored encrypted."""

    pass


def encrypt_bytes(data: bytes) -> bytes:
    """Encrypt raw bytes using the primary key."""
    return _get_fernet().encrypt(data)


def decrypt_bytes(data: bytes) -> bytes:
    """Decrypt raw bytes using any configured key."""
    return _get_fernet().decrypt(data)
