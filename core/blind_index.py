"""
Blind-index helper for searching encrypted fields.

A blind index is an HMAC-SHA256 hash of the plaintext, keyed with a secret
(BLIND_INDEX_KEY).  It allows exact-match lookups on encrypted columns without
exposing plaintext in the database.

Security properties:
  - Deterministic: the same plaintext + same key → same hash → searchable.
  - One-way: hash → plaintext is not feasible without the key.
  - Keyed: without BLIND_INDEX_KEY, an attacker with DB access cannot brute-force
    the hashes (unlike a bare SHA-256).
  - Key isolation: BLIND_INDEX_KEY must be kept separate from SECRET_KEY and
    FIELD_ENCRYPTION_KEY. In production, using SECRET_KEY as a fallback is prohibited.
  - Substring tokens limitation: when blind indexes are applied to substring tokens
    (e.g., trigrams in PatientSearchToken), the keyspace is small (~17.5k for Latin letters).
    Holders of BLIND_INDEX_KEY can precompute all token hashes. See known_limitations.md §1.

Usage:
    from core.blind_index import make_blind_index, search_by_blind_index

    Patient.objects.filter(national_id_hash=make_blind_index(raw_national_id))
"""

import hashlib
import hmac
import logging

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)


def _get_key() -> bytes:
    key = getattr(settings, "BLIND_INDEX_KEY", "")
    secret_key = getattr(settings, "SECRET_KEY", "")
    debug = getattr(settings, "DEBUG", True)

    if not key or (key == secret_key and not debug):
        if not debug:
            raise ImproperlyConfigured(
                "BLIND_INDEX_KEY must be set to an independent dedicated secret in production (DEBUG=False). "
                "Sharing or omitting BLIND_INDEX_KEY undermines cryptographic key isolation."
            )
        logger.warning(
            "BLIND_INDEX_KEY is unset or identical to SECRET_KEY; falling back to SECRET_KEY. "
            "In production, a dedicated BLIND_INDEX_KEY must be set."
        )
        key = secret_key

    if isinstance(key, str):
        key = key.encode("utf-8")
    return key


def make_blind_index(plaintext: str) -> str:
    """
    Return a 64-hex-char HMAC-SHA256 of the normalised plaintext.
    Empty/None input returns an empty string (so optional fields stay nullable).
    """
    if not plaintext:
        return ""
    normalised = plaintext.strip().lower()
    digest = hmac.new(_get_key(), normalised.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest
