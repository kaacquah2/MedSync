/**
 * Drug-Allergy Safety & Contraindication Engine (Client-side)
 *
 * Provides real-time contraindication detection for the prescription interface,
 * mirroring the server-side safety checks in records/allergy_checker.py.
 */

import { PatientAlert } from "@/types";

export interface AllergyConflict {
  allergyId: number;
  allergyLabel: string;
  severity: string;
  reaction?: string;
  drugPrescribed: string;
  conflictType: "EXACT_MATCH" | "CLASS_MATCH" | "CROSS_REACTIVITY";
  message: string;
}

interface DrugAllergyClass {
  className: string;
  allergenKeywords: string[];
  conflictingDrugs: string[];
  crossReactiveDrugs: string[];
}

const DRUG_ALLERGY_CLASSES: DrugAllergyClass[] = [
  {
    className: "Penicillins & Beta-lactams",
    allergenKeywords: [
      "penicillin", "amoxicillin", "ampicillin", "benzylpenicillin",
      "phenoxymethylpenicillin", "cloxacillin", "flucloxacillin", "piperacillin",
      "augmentin", "clavulanate", "co-amoxiclav", "beta-lactam", "beta lactam",
    ],
    conflictingDrugs: [
      "amoxicillin", "ampicillin", "benzylpenicillin", "phenoxymethylpenicillin",
      "cloxacillin", "flucloxacillin", "piperacillin", "augmentin", "clavulanate",
      "co-amoxiclav", "amoxil", "unasyn", "timentin",
    ],
    crossReactiveDrugs: [
      "ceftriaxone", "cefuroxime", "cefalexin", "cephalexin", "cefaclor",
      "cefazolin", "cefotaxime", "cefepime", "ceftazidime", "cefixime",
    ],
  },
  {
    className: "Sulfonamides (Sulfa)",
    allergenKeywords: [
      "sulfa", "sulfonamide", "co-trimoxazole", "cotrimoxazole", "bactrim",
      "septra", "sulfamethoxazole", "sulfadiazine", "sulfasalazine",
    ],
    conflictingDrugs: [
      "co-trimoxazole", "cotrimoxazole", "bactrim", "septra", "sulfamethoxazole",
      "sulfadiazine", "silver sulfadiazine", "sulfasalazine", "trimethoprim-sulfamethoxazole",
    ],
    crossReactiveDrugs: [],
  },
  {
    className: "NSAIDs & Salicylates",
    allergenKeywords: [
      "nsaid", "nsaids", "non-steroidal", "nonsteroidal", "aspirin",
      "ibuprofen", "diclofenac", "naproxen", "ketorolac", "indomethacin",
      "meloxicam", "piroxicam", "celecoxib",
    ],
    conflictingDrugs: [
      "aspirin", "ibuprofen", "diclofenac", "naproxen", "ketorolac",
      "indomethacin", "meloxicam", "piroxicam", "celecoxib", "acetylsalicylic acid",
    ],
    crossReactiveDrugs: [],
  },
  {
    className: "Opioids",
    allergenKeywords: [
      "opioid", "opiate", "morphine", "codeine", "tramadol",
      "fentanyl", "pethidine", "meperidine", "oxycodone", "hydromorphone",
    ],
    conflictingDrugs: [
      "morphine", "codeine", "tramadol", "fentanyl", "pethidine",
      "meperidine", "oxycodone", "hydromorphone", "dihydrocodeine",
    ],
    crossReactiveDrugs: [],
  },
  {
    className: "Macrolides",
    allergenKeywords: [
      "macrolide", "erythromycin", "azithromycin", "clarithromycin",
    ],
    conflictingDrugs: [
      "erythromycin", "azithromycin", "clarithromycin", "roxithromycin",
    ],
    crossReactiveDrugs: [],
  },
  {
    className: "Fluoroquinolones",
    allergenKeywords: [
      "fluoroquinolone", "quinolone", "ciprofloxacin", "levofloxacin",
      "moxifloxacin", "ofloxacin", "norfloxacin",
    ],
    conflictingDrugs: [
      "ciprofloxacin", "levofloxacin", "moxifloxacin", "ofloxacin",
      "norfloxacin", "cipro",
    ],
    crossReactiveDrugs: [],
  },
  {
    className: "Aminoglycosides",
    allergenKeywords: [
      "aminoglycoside", "gentamicin", "amikacin", "tobramycin",
      "streptomycin", "neomycin",
    ],
    conflictingDrugs: [
      "gentamicin", "amikacin", "tobramycin", "streptomycin", "neomycin",
    ],
    crossReactiveDrugs: [],
  },
  {
    className: "Tetracyclines",
    allergenKeywords: [
      "tetracycline", "doxycycline", "minocycline",
    ],
    conflictingDrugs: [
      "tetracycline", "doxycycline", "minocycline",
    ],
    crossReactiveDrugs: [],
  },
  {
    className: "Anticonvulsants",
    allergenKeywords: [
      "carbamazepine", "phenytoin", "phenobarbitone", "phenobarbital",
      "valproate", "sodium valproate", "valproic acid",
    ],
    conflictingDrugs: [
      "carbamazepine", "phenytoin", "phenobarbitone", "phenobarbital",
      "valproate", "sodium valproate", "valproic acid",
    ],
    crossReactiveDrugs: [],
  },
];

function normalizeText(text: string): string {
  if (!text) return "";
  const cleaned = text.toLowerCase().replace(/\b\d+([.,]\d+)?\s*(mg|g|mcg|ml|iu|%|iu\/ml|mg\/ml)?\b/g, " ");
  return cleaned.trim().replace(/\s+/g, " ");
}

export function checkAllergyConflicts(
  alerts: PatientAlert[] | undefined,
  drugName: string
): AllergyConflict[] {
  if (!alerts || !alerts.length || !drugName.trim()) {
    return [];
  }

  const activeAllergies = alerts.filter((a) => a.is_active && a.kind === "ALLERGY");
  if (!activeAllergies.length) return [];

  const normDrug = normalizeText(drugName);
  const drugTokens = new Set(normDrug.match(/[a-z]+/g) || []);

  const conflicts: AllergyConflict[] = [];

  for (const alert of activeAllergies) {
    const rawLabel = alert.label || "";
    const normAllergy = normalizeText(rawLabel);
    const allergyTokens = new Set(normAllergy.match(/[a-z]+/g) || []);
    const severity = alert.severity || "MODERATE";
    const reaction = alert.reaction || "";

    let matched = false;

    // 1. Direct name / token match
    for (const aToken of allergyTokens) {
      if (aToken.length >= 4) {
        if (normDrug.includes(aToken) || Array.from(drugTokens).some((dt) => dt.includes(aToken))) {
          conflicts.push({
            allergyId: alert.id,
            allergyLabel: rawLabel,
            severity,
            reaction,
            drugPrescribed: drugName,
            conflictType: "EXACT_MATCH",
            message: `Documented allergy to '${rawLabel}' (${severity}). Prescribing '${drugName}' is contraindicated.`,
          });
          matched = true;
          break;
        }
      }
    }

    if (matched) continue;

    // 2. Class and cross-reactivity match
    for (const drugClass of DRUG_ALLERGY_CLASSES) {
      const allergyInClass = drugClass.allergenKeywords.some(
        (kw) => normAllergy.includes(kw) || Array.from(allergyTokens).some((t) => t.includes(kw))
      );
      if (!allergyInClass) continue;

      const drugInClass = drugClass.conflictingDrugs.some(
        (cd) => normDrug.includes(cd) || Array.from(drugTokens).some((t) => t.includes(cd))
      );
      if (drugInClass) {
        conflicts.push({
          allergyId: alert.id,
          allergyLabel: rawLabel,
          severity,
          reaction,
          drugPrescribed: drugName,
          conflictType: "CLASS_MATCH",
          message: `Class contraindication (${drugClass.className}): Patient has documented allergy to '${rawLabel}' (${severity}). '${drugName}' belongs to the same therapeutic class.`,
        });
        matched = true;
        break;
      }

      const drugCrossReactive = drugClass.crossReactiveDrugs.some(
        (crd) => normDrug.includes(crd) || Array.from(drugTokens).some((t) => t.includes(crd))
      );
      if (drugCrossReactive) {
        conflicts.push({
          allergyId: alert.id,
          allergyLabel: rawLabel,
          severity,
          reaction,
          drugPrescribed: drugName,
          conflictType: "CROSS_REACTIVITY",
          message: `Cross-reactivity alert (${drugClass.className}): Patient has documented allergy to '${rawLabel}' (${severity}). '${drugName}' exhibits cross-reactivity.`,
        });
        matched = true;
        break;
      }
    }
  }

  return conflicts;
}
