"""
Clinical Drug-Allergy Checking and Contraindication Engine.

Performs cross-checks between a patient's active documented allergies
(PatientAlert where kind="ALLERGY" and is_active=True) and prescribed medications,
accounting for therapeutic drug classes, common brand names, and cross-reactivities.
"""

from dataclasses import dataclass
import re
from typing import Optional


@dataclass
class AllergyConflict:
    allergy_id: int
    allergy_label: str
    severity: str
    reaction: str
    drug_prescribed: str
    conflict_type: str  # "EXACT_MATCH", "CLASS_MATCH", "CROSS_REACTIVITY"
    message: str


# Drug class definition mapping allergen keywords to conflicting drug keywords
DRUG_ALLERGY_CLASSES = [
    {
        "class_name": "Penicillins & Beta-lactams",
        "allergen_keywords": [
            "penicillin", "amoxicillin", "ampicillin", "benzylpenicillin",
            "phenoxymethylpenicillin", "cloxacillin", "flucloxacillin", "piperacillin",
            "augmentin", "clavulanate", "co-amoxiclav", "beta-lactam", "beta lactam",
        ],
        "conflicting_drugs": [
            "amoxicillin", "ampicillin", "benzylpenicillin", "phenoxymethylpenicillin",
            "cloxacillin", "flucloxacillin", "piperacillin", "augmentin", "clavulanate",
            "co-amoxiclav", "amoxil", "unasyn", "timentin",
        ],
        "cross_reactive_drugs": [
            "ceftriaxone", "cefuroxime", "cefalexin", "cephalexin", "cefaclor",
            "cefazolin", "cefotaxime", "cefepime", "ceftazidime", "cefixime",
        ],
    },
    {
        "class_name": "Sulfonamides (Sulfa)",
        "allergen_keywords": [
            "sulfa", "sulfonamide", "co-trimoxazole", "cotrimoxazole", "bactrim",
            "septra", "sulfamethoxazole", "sulfadiazine", "sulfasalazine",
        ],
        "conflicting_drugs": [
            "co-trimoxazole", "cotrimoxazole", "bactrim", "septra", "sulfamethoxazole",
            "sulfadiazine", "silver sulfadiazine", "sulfasalazine", "trimethoprim-sulfamethoxazole",
        ],
        "cross_reactive_drugs": [],
    },
    {
        "class_name": "NSAIDs & Salicylates",
        "allergen_keywords": [
            "nsaid", "nsaids", "non-steroidal", "nonsteroidal", "aspirin",
            "ibuprofen", "diclofenac", "naproxen", "ketorolac", "indomethacin",
            "meloxicam", "piroxicam", "celecoxib",
        ],
        "conflicting_drugs": [
            "aspirin", "ibuprofen", "diclofenac", "naproxen", "ketorolac",
            "indomethacin", "meloxicam", "piroxicam", "celecoxib", "acetylsalicylic acid",
        ],
        "cross_reactive_drugs": [],
    },
    {
        "class_name": "Opioids",
        "allergen_keywords": [
            "opioid", "opiate", "morphine", "codeine", "tramadol",
            "fentanyl", "pethidine", "meperidine", "oxycodone", "hydromorphone",
        ],
        "conflicting_drugs": [
            "morphine", "codeine", "tramadol", "fentanyl", "pethidine",
            "meperidine", "oxycodone", "hydromorphone", "dihydrocodeine",
        ],
        "cross_reactive_drugs": [],
    },
    {
        "class_name": "Macrolides",
        "allergen_keywords": [
            "macrolide", "erythromycin", "azithromycin", "clarithromycin",
        ],
        "conflicting_drugs": [
            "erythromycin", "azithromycin", "clarithromycin", "roxithromycin",
        ],
        "cross_reactive_drugs": [],
    },
    {
        "class_name": "Fluoroquinolones",
        "allergen_keywords": [
            "fluoroquinolone", "quinolone", "ciprofloxacin", "levofloxacin",
            "moxifloxacin", "ofloxacin", "norfloxacin",
        ],
        "conflicting_drugs": [
            "ciprofloxacin", "levofloxacin", "moxifloxacin", "ofloxacin",
            "norfloxacin", "cipro",
        ],
        "cross_reactive_drugs": [],
    },
    {
        "class_name": "Aminoglycosides",
        "allergen_keywords": [
            "aminoglycoside", "gentamicin", "amikacin", "tobramycin",
            "streptomycin", "neomycin",
        ],
        "conflicting_drugs": [
            "gentamicin", "amikacin", "tobramycin", "streptomycin", "neomycin",
        ],
        "cross_reactive_drugs": [],
    },
    {
        "class_name": "Tetracyclines",
        "allergen_keywords": [
            "tetracycline", "doxycycline", "minocycline",
        ],
        "conflicting_drugs": [
            "tetracycline", "doxycycline", "minocycline",
        ],
        "cross_reactive_drugs": [],
    },
    {
        "class_name": "Anticonvulsants",
        "allergen_keywords": [
            "carbamazepine", "phenytoin", "phenobarbitone", "phenobarbital",
            "valproate", "sodium valproate", "valproic acid",
        ],
        "conflicting_drugs": [
            "carbamazepine", "phenytoin", "phenobarbitone", "phenobarbital",
            "valproate", "sodium valproate", "valproic acid",
        ],
        "cross_reactive_drugs": [],
    },
]


def _normalize_text(text: str) -> str:
    """Lowercase and remove non-alphanumeric punctuation except hyphens."""
    if not text:
        return ""
    # Strip strength/dosage suffix like 500mg, 10IU/ml, 250mcg, etc.
    cleaned = re.sub(r"\b\d+([.,]\d+)?\s*(mg|g|mcg|ml|iu|%|iu/ml|mg/ml)?\b", " ", text.lower())
    return " ".join(cleaned.split())


def check_prescription_allergies(
    patient,
    drug_name: str,
    rxnorm_code: Optional[str] = None,
) -> list[AllergyConflict]:
    """
    Checks if a prescribed drug conflicts with any of the patient's active allergies.
    Returns a list of AllergyConflict instances.
    """
    if not patient or not drug_name:
        return []

    # Retrieve all active ALLERGY alerts for the patient
    alerts = patient.alerts.filter(is_active=True, kind="ALLERGY")
    if not alerts.exists():
        return []

    normalized_drug = _normalize_text(drug_name)
    drug_tokens = set(re.findall(r"[a-z]+", normalized_drug))

    conflicts: list[AllergyConflict] = []

    for alert in alerts:
        raw_label = str(alert.label or "").strip()
        normalized_allergy = _normalize_text(raw_label)
        allergy_tokens = set(re.findall(r"[a-z]+", normalized_allergy))
        severity = getattr(alert, "severity", "MODERATE")
        reaction = str(getattr(alert, "reaction", "") or "").strip()

        matched = False

        # 1. Direct name/token match (e.g. Paracetamol allergy vs Paracetamol 500mg)
        for a_token in allergy_tokens:
            if len(a_token) >= 4:
                # Check direct inclusion or token match
                if a_token in normalized_drug or any(a_token in d_token for d_token in drug_tokens):
                    conflicts.append(
                        AllergyConflict(
                            allergy_id=alert.id,
                            allergy_label=raw_label,
                            severity=severity,
                            reaction=reaction,
                            drug_prescribed=drug_name,
                            conflict_type="EXACT_MATCH",
                            message=(
                                f"Direct allergy conflict: Patient has a documented allergy to "
                                f"'{raw_label}' ({severity}). Prescribing '{drug_name}' is contraindicated."
                            ),
                        )
                    )
                    matched = True
                    break

        if matched:
            continue

        # 2. Drug class and cross-reactivity matches
        for drug_class in DRUG_ALLERGY_CLASSES:
            # Check if allergy matches this class
            allergy_in_class = any(
                kw in normalized_allergy or any(kw in tok for tok in allergy_tokens)
                for kw in drug_class["allergen_keywords"]
            )
            if not allergy_in_class:
                continue

            # Check if prescribed drug belongs to this class
            drug_in_class = any(
                cd in normalized_drug or any(cd in tok for tok in drug_tokens)
                for cd in drug_class["conflicting_drugs"]
            )
            if drug_in_class:
                conflicts.append(
                    AllergyConflict(
                        allergy_id=alert.id,
                        allergy_label=raw_label,
                        severity=severity,
                        reaction=reaction,
                        drug_prescribed=drug_name,
                        conflict_type="CLASS_MATCH",
                        message=(
                            f"Class contraindication ({drug_class['class_name']}): Patient has documented "
                            f"allergy to '{raw_label}' ({severity}). '{drug_name}' belongs to the same therapeutic class."
                        ),
                    )
                )
                matched = True
                break

            # Check cross-reactivity (e.g. Penicillin allergy + Cephalosporin)
            drug_cross_reactive = any(
                crd in normalized_drug or any(crd in tok for tok in drug_tokens)
                for crd in drug_class["cross_reactive_drugs"]
            )
            if drug_cross_reactive:
                conflicts.append(
                    AllergyConflict(
                        allergy_id=alert.id,
                        allergy_label=raw_label,
                        severity=severity,
                        reaction=reaction,
                        drug_prescribed=drug_name,
                        conflict_type="CROSS_REACTIVITY",
                        message=(
                            f"Cross-reactivity warning ({drug_class['class_name']}): Patient has documented "
                            f"allergy to '{raw_label}' ({severity}). '{drug_name}' exhibits significant cross-reactivity."
                        ),
                    )
                )
                matched = True
                break

    return conflicts
