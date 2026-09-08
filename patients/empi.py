"""
Enterprise Master Patient Index (EMPI) — patient identity matching.

Purpose:
  Ensure that "Patient A at Hospital 1" and "Patient A at Hospital 2" resolve
  to the SAME Person record in the central registry, preventing duplicate records
  that fragment care history.

Matching strategy (§18 EMPI requirement):
  1. DETERMINISTIC (high confidence)
     - Ghana Card national ID:  exact match on national_id_hash (HMAC-SHA256).
       This is the primary identifier.  If matched → same person.

  2. PROBABILISTIC (medium confidence — candidate alert, not auto-merge)
     - name_hash (exact blind-index match on "first last") AND matching date_of_birth.
       Shown as a WARNING to the registering clinician; manual review required
       before treating as a duplicate.

  3. CONFLICT
     - Two different candidates match on national ID but have different names/DOBs.
       Escalate to MANUAL_REVIEW with both candidates surfaced.

Confidence tiers returned:
  "exact"        — deterministic national-ID match; almost certainly same person.
  "probable"     — name + DOB match; recommend review.
  "conflict"     — multiple contradictory matches; must be reviewed before admission.
  "no_match"     — nothing found; safe to register as a new patient.

Production notes:
  - A real EMPI would use weighted Jaro-Winkler / Soundex / ML scoring across
    many fields.  This implementation covers the deterministic primary key and
    one probabilistic fallback — sufficient to demonstrate the concept.
  - The O(n) date_of_birth comparison in the probabilistic path is acceptable for
    a prototype.  Production would add a non-encrypted DOB index or a hash thereof.
  - Merging / de-duplication (when two records turn out to be the same person) is
    a complex clinical workflow outside this prototype's scope.

See also: docs/adr/005-empi-approach.md
"""

from dataclasses import dataclass, field
from typing import Literal

from core.blind_index import make_blind_index

MatchConfidence = Literal["exact", "probable", "conflict", "no_match"]


@dataclass
class MatchResult:
    confidence: MatchConfidence
    candidates: list = field(default_factory=list)
    message: str = ""


def soundex(text: str) -> str:
    """Return Soundex codes for words in text."""
    words = text.split()
    codes = []
    mapping = {
        "B": "1",
        "F": "1",
        "P": "1",
        "V": "1",
        "C": "2",
        "G": "2",
        "J": "2",
        "K": "2",
        "Q": "2",
        "S": "2",
        "X": "2",
        "Z": "2",
        "D": "3",
        "T": "3",
        "L": "4",
        "M": "5",
        "N": "5",
        "R": "6",
    }
    for word in words:
        clean = "".join(c.upper() for c in word if c.isalpha())
        if not clean:
            continue
        first = clean[0]
        res = [first]
        prev = mapping.get(first, "")
        for char in clean[1:]:
            digit = mapping.get(char, "")
            if digit and digit != prev:
                res.append(digit)
                if len(res) == 4:
                    break
            prev = digit
        while len(res) < 4:
            res.append("0")
        codes.append("".join(res))
    return " ".join(codes)


def match_patient(
    national_id: str = "",
    name: str = "",
    dob: str = "",
) -> MatchResult:
    """
    Search the central patient registry for existing records matching the
    supplied identifiers.

    Parameters
    ----------
    national_id : Ghana Card or passport number (plaintext, unhashed).
    name        : "FirstName LastName" (case-insensitive).
    dob         : Date of birth as "YYYY-MM-DD" string.

    Returns a MatchResult with confidence tier and list of candidate Patient objects.
    """
    from .models import Patient, PatientSearchToken, generate_name_trigrams

    # ── 1. Deterministic: national ID ────────────────────────────────────
    if national_id.strip():
        nid_hash = make_blind_index(national_id.strip())
        nid_matches = list(
            Patient.objects.filter(national_id_hash=nid_hash).select_related(
                "registered_at_hospital"
            )
        )
        if len(nid_matches) == 1:
            return MatchResult(
                confidence="exact",
                candidates=nid_matches,
                message=(
                    f"Ghana Card / national ID matches existing patient "
                    f"{nid_matches[0].universal_id}."
                ),
            )
        if len(nid_matches) > 1:
            return MatchResult(
                confidence="conflict",
                candidates=nid_matches,
                message=(
                    f"National ID '{national_id}' matches {len(nid_matches)} records. "
                    "Manual review required before registration."
                ),
            )

    # ── 2. Probabilistic: name + DOB ─────────────────────────────────────
    if name.strip():
        name_hash = make_blind_index(name.strip())
        name_matches = list(
            Patient.objects.filter(name_hash=name_hash).select_related("registered_at_hospital")
        )

        # Filter by DOB if provided (decrypt-and-compare; O(n) over name matches)
        if dob.strip() and name_matches:
            name_matches = [
                p for p in name_matches if str(p.date_of_birth or "").strip() == dob.strip()
            ]

        if name_matches:
            return MatchResult(
                confidence="probable",
                candidates=name_matches,
                message=(
                    f"Name{' + date-of-birth' if dob else ''} match "
                    f"{len(name_matches)} existing record(s). "
                    "Review before creating a new patient."
                ),
            )

        # Phonetic (Soundex) fallback if exact blind index misses
        if dob.strip():
            target_soundex = soundex(name.strip())
            phonetic_matches = []

            # Pre-filter candidates using blind-indexed trigrams to avoid full-table O(N) scan
            trigrams = generate_name_trigrams(name.strip(), "")
            token_hashes = [make_blind_index(t) for t in trigrams if t]

            if token_hashes:
                candidate_ids = list(
                    PatientSearchToken.objects.filter(token_hash__in=token_hashes)
                    .values_list("patient_id", flat=True)
                    .distinct()
                )
                candidates_qs = Patient.objects.filter(id__in=candidate_ids).select_related(
                    "registered_at_hospital"
                )
            else:
                candidates_qs = Patient.objects.all().select_related("registered_at_hospital")[:500]

            for p in candidates_qs:
                if str(p.date_of_birth or "").strip() == dob.strip():
                    p_full_name = f"{p.first_name} {p.last_name}".strip()
                    if soundex(p_full_name) == target_soundex:
                        phonetic_matches.append(p)
            if phonetic_matches:
                return MatchResult(
                    confidence="probable",
                    candidates=phonetic_matches,
                    message=(
                        f"Phonetic name + date-of-birth match "
                        f"{len(phonetic_matches)} existing record(s). "
                        "Review before creating a new patient."
                    ),
                )

    return MatchResult(confidence="no_match", message="No existing patient found.")
