# ADR-003: FHIR Adoption Strategy

**Date:** 2026-06-26
**Status:** Accepted (subset implementation)

## Context

HL7 FHIR R4 is the dominant standard for healthcare data interoperability. The checklist (§18) requires a FHIR-shaped data model and, ideally, a FHIR-conformant API. Full FHIR conformance (CapabilityStatement, search parameters, subscriptions, terminology server integration) is a significant engineering effort.

## Decision

Implement a **FHIR R4 subset**:

1. **Data model shaped on FHIR resources**: `Patient`, `Encounter`, `Condition` (Diagnosis), `MedicationRequest` (Prescription), `Observation` (LabResult). These are Django models — not native FHIR resources — but field names and structure follow FHIR semantics where practical.

2. **Structured terminology codes**: `Diagnosis.icd_code` (ICD-10), `Diagnosis.snomed_code` (SNOMED CT optional), `LabResult.loinc_code` (LOINC optional), `Prescription.rxnorm_code` (RxNorm optional). Coded data enables machine-readable interoperability without free-text ambiguity.

3. **Read-only FHIR API** (`fhir/` module): `GET /fhir/Patient/<nhid>/` and `GET /fhir/Patient/<nhid>/$everything` return valid FHIR R4 JSON. Access-gated via `can_access_patient()`; audited.

4. **Document what's out of scope**: FHIR search parameters (`?name=`, `?birthdate=`), CapabilityStatement (`/metadata`), write operations (FHIR `PUT`/`POST`), subscriptions, and full conformance testing are explicitly deferred.

## Rationale

- Demonstrates portability without the full engineering overhead of a FHIR server.
- A single `patient_to_fhir()` mapper is more defensible than claiming full conformance.
- Structured codes (ICD-10 etc.) are independently valuable for analytics and future integration, regardless of the FHIR API.

## Legacy interop note

Where existing hospital systems feed the centralized store, the integration architecture would be:
- **HL7 v2 ADT/ORU feeds** from legacy HIS: a message queue (RabbitMQ or Kafka) with adapters translating v2 segments to FHIR resources, then POSTing to the EMR API.
- **DICOM imaging**: DICOM viewer (e.g. Orthanc) linked by Encounter; DICOM metadata stored as a URL reference in clinical notes.

## What a real production deployment would add

- Full FHIR R4 conformance via a dedicated FHIR server (HAPI FHIR or Azure Health Data Services).
- SMART on FHIR for patient-facing apps.
- FHIR subscriptions for real-time event propagation to other hospitals.
- Terminology server (SNOMED/LOINC/RxNorm) for code validation and value-set lookups.
