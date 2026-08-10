# ADR-004: EMPI — Patient Identity Matching Approach

**Date:** 2026-06-26
**Status:** Accepted

## Context

When a patient presents at a hospital that has not seen them before, the registering clinician must determine whether the patient already exists in the central registry. Duplicate records fragment care history and create dangerous situations (e.g. duplicate medication orders, missing allergy records).

## Decision

A two-tier matching strategy using existing blind-index infrastructure:

### Tier 1 — Deterministic (Ghana Card national ID)

The Ghana Card national ID (`national_id`) is the **primary patient identifier**. It is:
- Encrypted at rest (Fernet); the plaintext never appears in the DB.
- Blind-indexed (`national_id_hash = HMAC-SHA256(normalised_national_id)`).
- Used for O(log n) exact-match lookup: `Patient.objects.filter(national_id_hash=make_blind_index(nid))`.

A match on national ID is treated as **"exact"** — the patient almost certainly already exists; the clinician is blocked from creating a duplicate and shown the existing NHID.

### Tier 2 — Probabilistic (name + date-of-birth)

If no national ID is provided (or if it's unavailable), the system:
1. Computes the blind index of "FirstName LastName" and queries `name_hash`.
2. Filters the name matches by `date_of_birth` string comparison (decrypt-and-compare on the small result set).
3. Returns confidence = **"probable"** if matches are found.

The clinician sees a warning with the candidate patient(s) and must explicitly confirm they are registering a new (distinct) person.

### Conflict

If a national ID matches more than one record (data integrity violation), or if probabilistic matches are contradictory, confidence = **"conflict"** and a manual review is required.

### Implementation

`patients/empi.py::match_patient(national_id, name, dob)` — called from `patients/views.py::patient_create`.

## Rationale

- Reuses existing blind-index infrastructure (no new columns or search infrastructure needed).
- Ghana Card is the strongest identifier available in Ghana; aligns with national health policy.
- Soft-blocking (warning + confirm) for probabilistic matches prevents over-blocking while still surfacing likely duplicates.

## Consequences

- A patient without a national ID relies only on name+DOB matching, which has higher false-positive and false-negative rates.
- The O(n) DOB comparison on name matches is acceptable for a prototype. Production would add a hashed DOB index.

## What a real production deployment would add

- Weighted probabilistic matching (Jaro-Winkler name similarity, phonetic codes) with a configurable confidence threshold.
- A dedicated EMPI service (e.g. OpenEMPI or commercial) handling merge/unmerge workflows.
- Patient MPI managed via the IHE PIX/PDQ profile for HL7 v2 interoperability.
- Cross-reference link records when two NHIDs are determined to be the same person (without deleting either record — clinical legal requirement).
