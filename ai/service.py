"""
AI query service — grounded clinical decision support.

Architecture:
  - Provider abstraction: local Ollama (production, zero egress) or Gemini (development/testing only)
  - Production compliance: In production, AI_PROVIDER=ollama is required. Ollama runs
    within the local/hospital boundary with zero PHI egress (bypassing outbound proxies),
    complying with HIPAA and Ghana Data Protection Act 2012.
  - Development provider: Gemini is supported for local development and testing only (DEBUG=True).
    Sending clinical records to external cloud APIs involves egress of Protected Health Information (PHI);
    the free tier provides no BAA or DPA, and partial field masking does not constitute legal de-identification.
  - Grounding: answers drawn ONLY from the patient's records the caller is
    authorised to see — never from the model's training data
  - All queries audited via log_action("AI_QUERY")
  - Hard guardrails enforced in the prompt (cite records, refuse if unknown)

Configuration:
  1. Production / Recommended (Ollama):
     - Install Ollama: https://ollama.com
     - `ollama pull llama3.1:8b`
     - Set AI_PROVIDER=ollama (default)
     - Zero PHI leaves the server.

  2. Development only (Gemini):
     - Requires DEBUG=True.
     - ALLOW_EXTERNAL_AI_IN_PRODUCTION MUST be False in any real production deployment.
       Overriding this flag to True enables cross-border egress of special personal health
       data to Google cloud APIs, violating Ghana Data Protection Act 2012 (Act 843 §47)
       without prior Data Protection Commission (DPC) transfer authorization.
     - Add GEMINI_API_KEY=<key> to your .env
     - Set AI_PROVIDER=gemini
"""

from __future__ import annotations

import logging
import re

from django.conf import settings

logger = logging.getLogger(__name__)

# ── Grounded system prompt ─────────────────────────────────────────────────────

_SYSTEM_PROMPT_HEADER = """You are a clinical decision-support assistant embedded in the \
MedSync EMR system. A clinician is querying you about a specific patient.

STRICT RULES:
1. Answer ONLY using information present in the <PATIENT_RECORDS> section below.
2. If you cannot answer from the records, say "I cannot find information about that \
in the available records."
3. Cite every claim with an inline reference like [Encounter 1], [Diagnosis 2], \
[Lab Result 3], [Vitals 2026-01-15]. Use exact labels from the records.
4. Never speculate, never use external medical knowledge not present in the records.
5. Keep the response concise and clinically precise.
6. If you detect a potential drug interaction, allergy conflict, or critical abnormal \
result, explicitly flag it with ⚠️ WARNING."""


def _build_user_prompt(context: str, question: str) -> str:
    """Assemble the user prompt containing patient records and clinician question.

    Closing XML tags and structural prompt delimiters in context are escaped.
    """
    safe_context = context.replace("</", "< /").replace("CLINICIAN QUESTION:", "QUESTION:")
    safe_question = question.strip().replace("</", "< /")
    return (
        "<PATIENT_RECORDS>\n"
        + safe_context
        + "\n</PATIENT_RECORDS>\n\n"
        + "CLINICIAN QUESTION: "
        + safe_question
        + "\n\nRESPONSE (with inline citations):"
    )


# ── Context builder ────────────────────────────────────────────────────────────


def build_patient_context(
    patient,
    encounters,
    records,
    vitals,
    deidentify: bool = False,
    mask_identifiers: bool | None = None,
) -> str:
    """
    Build a text context block from the patient's records for use in the AI prompt.
    Only includes data the caller has already been authorised to see.
    Encrypted fields decrypt transparently when accessed as Python attributes.

    WARNING ON DE-IDENTIFICATION:
    Setting mask_identifiers=True (or legacy deidentify=True) masks direct identifiers
    (NHID, exact DOB -> age, facility name), but does NOT constitute legal de-identification
    under HIPAA Safe Harbor (§164.514(b)(2)) or Ghana Data Protection Act 2012.
    Unstructured clinical notes, encounter dates, vitals timestamps, and diagnostic narratives
    remain present and can contain re-identifying details.
    """
    if mask_identifiers is None:
        mask_identifiers = deidentify

    lines: list[str] = []

    # Demographics
    lines.append("== PATIENT INFORMATION ==")
    if mask_identifiers:
        lines.append("NHID: NHID-REDACTED")
        try:
            from datetime import date

            dob_str = patient.date_of_birth
            parts = [int(p) for p in dob_str.split("-")]
            if len(parts) == 3:
                birth = date(parts[0], parts[1], parts[2])
                today = date.today()
                age = (
                    today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))
                )
                lines.append(f"Age: {age}")
            else:
                lines.append("Age: Unknown")
        except Exception as exc:
            logger.warning(
                "Failed to parse date_of_birth for age calculation (patient=%s): %s",
                getattr(patient, "universal_id", "?"),
                exc,
            )
            lines.append("Age: Unknown")
    else:
        lines.append(f"NHID: {patient.universal_id}")
        try:
            lines.append(f"Date of Birth: {patient.date_of_birth}")
        except Exception as exc:
            logger.warning(
                "Failed to format date_of_birth for patient %s: %s",
                getattr(patient, "universal_id", "?"),
                exc,
            )

    lines.append(f"Sex: {patient.get_sex_display()}")
    lines.append(f"Blood Group: {patient.blood_group}")

    # Active alerts / allergies
    alerts = patient.alerts.filter(is_active=True)
    if alerts.exists():
        lines.append("\n== ACTIVE ALERTS / ALLERGIES ==")
        for a in alerts:
            try:
                lines.append(
                    f"  [{a.get_kind_display()}] {a.label} — "
                    f"Severity: {a.get_severity_display()}"
                    + (f" — Reaction: {a.reaction}" if a.reaction else "")
                )
            except Exception as exc:
                logger.warning(
                    "Failed to format alert %s for patient %s: %s",
                    getattr(a, "pk", "?"),
                    getattr(patient, "universal_id", "?"),
                    exc,
                )

    # Vitals
    if vitals:
        lines.append("\n== VITAL SIGNS (most recent first) ==")
        for i, v in enumerate(vitals[:6], 1):
            parts = [f"[Vitals {i} — {v.recorded_at.strftime('%Y-%m-%d %H:%M')}]"]
            if v.temperature:
                parts.append(f"Temp {v.temperature}°C")
            if v.heart_rate:
                parts.append(f"HR {v.heart_rate} bpm")
            if v.bp_systolic and v.bp_diastolic:
                parts.append(f"BP {v.bp_systolic}/{v.bp_diastolic} mmHg")
            if v.spo2:
                parts.append(f"SpO₂ {v.spo2}%")
            if v.pain_score is not None:
                parts.append(f"Pain {v.pain_score}/10")
            lines.append("  " + ", ".join(parts))

    # Encounters with nested clinical data
    if encounters:
        lines.append(f"\n== ENCOUNTERS ({len(encounters)} total) ==")
        for i, enc in enumerate(encounters[:10], 1):
            try:
                hosp_name = (
                    "Facility Redacted"
                    if mask_identifiers
                    else (enc.created_at_hospital.name if enc.created_at_hospital else "Unknown")
                )
                lines.append(
                    f"\n[Encounter {i}] "
                    f"{enc.get_encounter_type_display()} — "
                    f"{enc.created_at.strftime('%Y-%m-%d')} — "
                    f"{hosp_name}"
                )
                if enc.chief_complaint:
                    lines.append(f"  Chief Complaint: {enc.chief_complaint}")
                if enc.notes:
                    lines.append(f"  Clinical Notes: {enc.notes[:500]}")

                # Diagnoses
                for j, d in enumerate(enc.diagnoses.all(), 1):
                    try:
                        icd = f" ({d.icd_code})" if d.icd_code else ""
                        lines.append(f"  [Diagnosis {i}.{j}]{icd}: {d.description}")
                    except Exception as exc:
                        logger.warning(
                            "Failed to format diagnosis %s in encounter %s: %s",
                            getattr(d, "pk", "?"),
                            getattr(enc, "pk", "?"),
                            exc,
                        )

                # Prescriptions
                for j, rx in enumerate(enc.prescriptions.all(), 1):
                    try:
                        lines.append(
                            f"  [Prescription {i}.{j}]: {rx.drug_name} — "
                            f"{rx.dosage}, {rx.frequency}"
                        )
                    except Exception as exc:
                        logger.warning(
                            "Failed to format prescription %s in encounter %s: %s",
                            getattr(rx, "pk", "?"),
                            getattr(enc, "pk", "?"),
                            exc,
                        )

                # Lab results
                for j, lab in enumerate(enc.lab_results.all(), 1):
                    try:
                        flag = " ⚠️ ABNORMAL" if lab.is_abnormal else ""
                        ref = f" (ref: {lab.reference_range})" if lab.reference_range else ""
                        lines.append(
                            f"  [Lab Result {i}.{j}]: {lab.test_name} — "
                            f"{lab.result_value}{ref}{flag}"
                        )
                    except Exception as exc:
                        logger.warning(
                            "Failed to format lab result %s in encounter %s: %s",
                            getattr(lab, "pk", "?"),
                            getattr(enc, "pk", "?"),
                            exc,
                        )
            except Exception as exc:
                logger.warning(
                    "Failed to format encounter %s for patient %s: %s",
                    getattr(enc, "pk", "?"),
                    getattr(patient, "universal_id", "?"),
                    exc,
                )

    return "\n".join(lines)


# ── Provider calls ─────────────────────────────────────────────────────────────


def _call_gemini(user_prompt: str, system_instruction: str = _SYSTEM_PROMPT_HEADER) -> str:
    """Call Gemini 2.5 Flash via the google-generativeai SDK with system_instruction structural separation."""
    try:
        import google.generativeai as genai

        genai.configure(api_key=settings.GEMINI_API_KEY)
        model = genai.GenerativeModel(
            model_name=settings.GEMINI_MODEL,
            system_instruction=system_instruction,
        )
        response = model.generate_content(user_prompt)
        return response.text
    except ImportError:
        raise RuntimeError(
            "google-generativeai is not installed. Run: pip install google-generativeai"
        ) from None
    except Exception as exc:
        logger.exception("Gemini API call failed")
        raise RuntimeError(f"Gemini API error: {exc}") from exc


def _call_ollama(user_prompt: str, system_instruction: str = _SYSTEM_PROMPT_HEADER) -> str:
    """Call a locally-running Ollama instance using /api/chat for structural system role separation.

    Bypasses HTTP proxies to guarantee zero egress outside the local host.
    """
    try:
        import requests

        base_url = settings.OLLAMA_BASE_URL.rstrip("/")
        url = f"{base_url}/api/chat"
        payload = {
            "model": settings.OLLAMA_MODEL,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
        }
        # Explicit zero-egress proxy bypass for local Ollama calls
        resp = requests.post(
            url,
            json=payload,
            timeout=120,
            proxies={"http": None, "https": None},
        )
        resp.raise_for_status()
        data = resp.json()
        if "message" in data and isinstance(data["message"], dict) and "content" in data["message"]:
            return data["message"]["content"]
        return data.get("response", "")
    except Exception as exc:
        logger.exception("Ollama API call failed")
        raise RuntimeError(f"Ollama error: {exc}") from exc


# ── Public entry point ─────────────────────────────────────────────────────────


def validate_citations(answer: str, context: str) -> str:
    """
    Scan the answer for inline citations of format [Citation Name]
    and verify they exist in the grounding context.
    If not, replace them with '[citation omitted]' to prevent hallucination propagation.

    Uses EXACT label-set matching (not substring) to prevent cases like
    [Encounter 11] passing validation when only [Encounter 1] exists in context.
    The valid set is built by scanning the context with the same regex, so only
    labels that actually appear as bracketed citations in context are accepted.
    """
    # Match bracketed text like [Encounter 1], [Diagnosis 1.2], etc.
    # Exclude emoji-bearing warnings like [⚠️ WARNING]
    pattern = re.compile(r"\[([A-Za-z0-9\s\-\:\.\u2014]+)\]")

    # Build the set of valid citation labels that actually appear in context
    valid_labels: set = {m.group(1).strip() for m in pattern.finditer(context)}

    def replace_citation(match: re.Match) -> str:
        full_citation = match.group(0)
        citation_content = match.group(1).strip()

        # Exact membership check — prevents substring false-positives
        if citation_content in valid_labels:
            return full_citation

        logger.warning("Hallucinated citation found and removed: %s", full_citation)
        return "[citation omitted]"

    return pattern.sub(replace_citation, answer)


def query_patient(patient, encounters, records, vitals, question: str) -> dict:
    """
    Ground-and-query: build context from authorised records, call the
    configured AI provider, return {answer, provider, model, context_size, retrieved_records}.

    Raises ValueError for invalid/excessive question length.
    Raises RuntimeError if the provider is misconfigured or unavailable.
    """
    if not question or not question.strip():
        raise ValueError("Question cannot be empty.")
    if len(question.strip()) > 1000:
        raise ValueError("Question exceeds maximum allowed length of 1000 characters.")

    provider = getattr(settings, "AI_PROVIDER", "ollama")

    if provider == "gemini":
        if not getattr(settings, "DEBUG", False):
            if not getattr(settings, "ALLOW_EXTERNAL_AI_IN_PRODUCTION", False):
                raise RuntimeError(
                    "The Gemini AI provider transmits Protected Health Information (PHI) to external Google "
                    "servers without a BAA/DPA and is restricted to development/testing environments (DEBUG=True). "
                    "Production deployments must use AI_PROVIDER=ollama for zero-egress local processing "
                    "under HIPAA and Ghana Data Protection Act 2012 (Act 843 §47)."
                )
            else:
                logger.critical(
                    "COMPLIANCE VIOLATION RISK: ALLOW_EXTERNAL_AI_IN_PRODUCTION=True overrides production safety checks "
                    "to transmit clinical health records to external Google Gemini endpoints. This constitutes an "
                    "unauthorized cross-border transfer of special personal data under Ghana Data Protection Act 2012 (Act 843 §47)."
                )
        if not getattr(settings, "GEMINI_API_KEY", ""):
            raise RuntimeError(
                "AI service is not configured. "
                "Add GEMINI_API_KEY=<your_key> to your .env file to enable AI queries. "
                "Get a free key at https://aistudio.google.com"
            )

    # In dev/test with external providers, mask direct identifiers (NHID, exact DOB, facility).
    # NOTE: This does NOT constitute HIPAA or Ghana DPA 2012 de-identification because
    # dates, vitals, diagnoses, and free-text clinical notes remain in the context payload.
    mask_identifiers = provider != "ollama"

    context = build_patient_context(
        patient, encounters, records, vitals, mask_identifiers=mask_identifiers
    )
    user_prompt = _build_user_prompt(context, question)

    # Collect record references for audit logging
    active_alerts = (
        list(patient.alerts.filter(is_active=True)) if hasattr(patient, "alerts") else []
    )
    retrieved_records = {
        "encounter_ids": [enc.id for enc in (encounters or [])],
        "vital_ids": [v.id for v in (vitals or [])],
        "alert_ids": [a.id for a in active_alerts],
    }

    try:
        if provider == "ollama":
            answer = _call_ollama(user_prompt, system_instruction=_SYSTEM_PROMPT_HEADER)
        else:
            answer = _call_gemini(user_prompt, system_instruction=_SYSTEM_PROMPT_HEADER)
    except Exception as exc:
        # Check if local fallback is enabled when external provider fails
        if provider != "ollama" and getattr(settings, "AI_ENABLE_FALLBACK", False):
            logger.warning(
                "Primary provider (%s) failed (%s). Attempting local Ollama fallback...",
                provider,
                exc,
            )
            try:
                answer = _call_ollama(user_prompt, system_instruction=_SYSTEM_PROMPT_HEADER)
                provider = "ollama (fallback)"
            except Exception as fallback_exc:
                logger.exception("Fallback provider (ollama) also failed")
                raise RuntimeError(
                    f"{provider.capitalize()} API error: {exc}. Fallback also failed: {fallback_exc}"
                ) from exc
        else:
            raise

    # Post-hoc citation validation to filter out hallucinated citations
    validated_answer = validate_citations(answer, context)

    return {
        "answer": validated_answer,
        "provider": provider,
        "model": settings.GEMINI_MODEL if provider == "gemini" else settings.OLLAMA_MODEL,
        "context_size": len(context),
        "retrieved_records": retrieved_records,
    }
