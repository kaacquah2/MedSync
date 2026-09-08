import { describe, it, expect } from "vitest";
import { checkAllergyConflicts } from "../utils/allergyChecker";
import { PatientAlert } from "@/types";

const mockPenicillinAlert: PatientAlert = {
  id: 1,
  kind: "ALLERGY",
  kind_display: "Allergy",
  label: "Penicillin",
  severity: "SEVERE",
  severity_display: "Severe",
  reaction: "Anaphylaxis and hives",
  recorded_by: null,
  recorded_at_hospital: null,
  is_active: true,
  is_high_risk: true,
  created_at: "2026-01-01T00:00:00Z",
};

const mockSulfaAlert: PatientAlert = {
  id: 2,
  kind: "ALLERGY",
  kind_display: "Allergy",
  label: "Sulfa drugs",
  severity: "MODERATE",
  severity_display: "Moderate",
  reaction: "Severe rash",
  recorded_by: null,
  recorded_at_hospital: null,
  is_active: true,
  is_high_risk: false,
  created_at: "2026-01-01T00:00:00Z",
};

const mockNsaidAlert: PatientAlert = {
  id: 3,
  kind: "ALLERGY",
  kind_display: "Allergy",
  label: "Aspirin & NSAIDs",
  severity: "LIFE_THREAT",
  severity_display: "Life-threatening",
  reaction: "Angioedema and bronchospasm",
  recorded_by: null,
  recorded_at_hospital: null,
  is_active: true,
  is_high_risk: true,
  created_at: "2026-01-01T00:00:00Z",
};

describe("allergyChecker", () => {
  it("detects direct penicillin conflict with Amoxicillin", () => {
    const conflicts = checkAllergyConflicts([mockPenicillinAlert], "Amoxicillin 500mg");
    expect(conflicts.length).toBeGreaterThanOrEqual(1);
    expect(conflicts[0].allergyLabel).toBe("Penicillin");
    expect(conflicts[0].severity).toBe("SEVERE");
    expect(conflicts[0].conflictType).toBe("CLASS_MATCH");
  });

  it("detects cross-reactivity between Penicillin and Ceftriaxone", () => {
    const conflicts = checkAllergyConflicts([mockPenicillinAlert], "Ceftriaxone 1g IV");
    expect(conflicts.length).toBeGreaterThanOrEqual(1);
    expect(conflicts[0].conflictType).toBe("CROSS_REACTIVITY");
  });

  it("does not flag non-conflicting medication for penicillin-allergic patient", () => {
    const conflicts = checkAllergyConflicts([mockPenicillinAlert], "Paracetamol 500mg");
    expect(conflicts).toHaveLength(0);
  });

  it("detects sulfa allergy with Co-trimoxazole", () => {
    const conflicts = checkAllergyConflicts([mockSulfaAlert], "Co-trimoxazole 480mg");
    expect(conflicts.length).toBeGreaterThanOrEqual(1);
    expect(conflicts[0].allergyLabel).toBe("Sulfa drugs");
    expect(conflicts[0].conflictType).toBe("CLASS_MATCH");
  });

  it("detects NSAID allergy with Ibuprofen and Diclofenac", () => {
    const conflictsIbu = checkAllergyConflicts([mockNsaidAlert], "Ibuprofen 400mg");
    expect(conflictsIbu.length).toBeGreaterThanOrEqual(1);

    const conflictsDiclo = checkAllergyConflicts([mockNsaidAlert], "Diclofenac 50mg");
    expect(conflictsDiclo.length).toBeGreaterThanOrEqual(1);
  });

  it("ignores inactive allergy alerts", () => {
    const inactivePenicillin = { ...mockPenicillinAlert, is_active: false };
    const conflicts = checkAllergyConflicts([inactivePenicillin], "Amoxicillin 500mg");
    expect(conflicts).toHaveLength(0);
  });

  it("detects direct substance match for unlisted classes", () => {
    const chloramphenicolAlert: PatientAlert = {
      ...mockPenicillinAlert,
      id: 99,
      label: "Chloramphenicol",
    };
    const conflicts = checkAllergyConflicts([chloramphenicolAlert], "Chloramphenicol 250mg");
    expect(conflicts.length).toBeGreaterThanOrEqual(1);
    expect(conflicts[0].conflictType).toBe("EXACT_MATCH");
  });

  it("returns empty array for invalid inputs", () => {
    expect(checkAllergyConflicts(undefined, "Amoxicillin")).toEqual([]);
    expect(checkAllergyConflicts([], "Amoxicillin")).toEqual([]);
    expect(checkAllergyConflicts([mockPenicillinAlert], "")).toEqual([]);
    expect(checkAllergyConflicts([mockPenicillinAlert], "   ")).toEqual([]);
  });
});
