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
  - Limitation: supports only exact-match queries, not substring/LIKE queries.
    Partial-name search still requires a Python-side scan (acceptable for prototype).

Usage:
    from core.blind_index import make_blind_index, search_by_blind_index

    Patient.objects.filter(national_id_hash=make_blind_index(raw_national_id))
"""

import hashlib
import hmac

from django.conf import settings


def _get_key() -> bytes:
    key = getattr(settings, "BLIND_INDEX_KEY", "")
    if not key:
        # Fallback for tests / early setup: use SECRET_KEY as the indexing key.
        # In production, a dedicated BLIND_INDEX_KEY must be set.
        key = settings.SECRET_KEY
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
