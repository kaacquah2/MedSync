import { describe, expect, it } from "vitest";
import {
  TRIAGE_COLORS,
  formatTriage,
  parseTriage,
} from "@/pages/common/EmergencyQueuePage";
import type { Appointment } from "@/types";

function mockAppointment(overrides: Partial<Appointment> = {}): Appointment {
  return {
    id: 1,
    patient: 1,
    patient_nhid: "NHID-001",
    patient_name: "Kwame Mensah",
    hospital: 1,
    hospital_name: "Accra Central",
    scheduled_for: "2026-09-08T10:00:00Z",
    duration_minutes: 30,
    appointment_type: "emergency",
    appointment_type_display: "Emergency",
    status: "checked_in",
    status_display: "Checked In",
    triage_acuity: null,
    reason: "",
    notes: "",
    created_at: "2026-09-08T09:50:00Z",
    ...overrides,
  };
}

describe("Emergency Triage Parsing & Clinical Safety", () => {
  it("uses first-class backend triage_acuity enum directly", () => {
    const apptRed = mockAppointment({
      triage_acuity: "RED",
      notes: "Severe trauma with shock",
    });
    const parsed = parseTriage(apptRed);
    expect(parsed.level).toBe("RED");
    expect(parsed.isUntriaged).toBe(false);
    expect(parsed.notes).toBe("Severe trauma with shock");

    const apptYellow = mockAppointment({
      triage_acuity: "YELLOW",
      notes: "Stable abdominal pain",
    });
    expect(parseTriage(apptYellow).level).toBe("YELLOW");
  });

  it("supports triage_level alias for backward compatibility", () => {
    const apptOrange = mockAppointment({
      triage_level: "ORANGE",
      notes: "High fever with tachycardia",
    });
    const parsed = parseTriage(apptOrange);
    expect(parsed.level).toBe("ORANGE");
    expect(parsed.isUntriaged).toBe(false);
  });

  it("strips legacy [Triage: LEVEL] prefix from notes when triage_acuity is set", () => {
    const appt = mockAppointment({
      triage_acuity: "RED",
      notes: "[Triage: RED] Massive hemorrhage",
    });
    const parsed = parseTriage(appt);
    expect(parsed.level).toBe("RED");
    expect(parsed.notes).toBe("Massive hemorrhage");
  });

  it("falls back to legacy [Triage: LEVEL] in notes for unmigrated records", () => {
    const apptLegacy = mockAppointment({
      triage_acuity: null,
      notes: "[Triage: ORANGE] Compound fracture",
    });
    const parsed = parseTriage(apptLegacy);
    expect(parsed.level).toBe("ORANGE");
    expect(parsed.isUntriaged).toBe(false);
    expect(parsed.notes).toBe("Compound fracture");
  });

  it("CLINICAL SAFETY: does NOT silently default dying patient to GREEN on format mismatch or missing data", () => {
    // Malformed notes or missing prefix — previously this silently became GREEN!
    const malformedCases = [
      "Cardiac arrest in ambulance bay",
      "[Triage: CRITICAL] Unresponsive patient",
      " [Triage: RED] extra leading space",
      "Triage RED - patient cyanotic",
      "",
    ];

    for (const badNote of malformedCases) {
      const appt = mockAppointment({
        triage_acuity: null,
        triage_level: null,
        notes: badNote,
        reason: badNote,
      });
      const parsed = parseTriage(appt);
      // It must NEVER be silently downgraded to GREEN
      expect(parsed.level).not.toBe("GREEN");
      expect(parsed.level).toBe("UNTRIAGED");
      expect(parsed.isUntriaged).toBe(true);
    }
  });

  it("has valid color mappings for all display levels including UNTRIAGED", () => {
    expect(TRIAGE_COLORS.RED).toBe("red");
    expect(TRIAGE_COLORS.ORANGE).toBe("orange");
    expect(TRIAGE_COLORS.YELLOW).toBe("yellow");
    expect(TRIAGE_COLORS.GREEN).toBe("green");
    expect(TRIAGE_COLORS.UNTRIAGED).toBe("red");
  });

  it("formats legacy triage string correctly", () => {
    expect(formatTriage("RED", "Chest trauma")).toBe("[Triage: RED] Chest trauma");
  });
});

describe("Emergency Queue Sorting Priority", () => {
  it("prioritizes UNTRIAGED and RED at the top, then ORANGE, YELLOW, GREEN", () => {
    const levelScore: Record<string, number> = {
      UNTRIAGED: 5,
      RED: 4,
      ORANGE: 3,
      YELLOW: 2,
      GREEN: 1,
    };

    const patients = [
      mockAppointment({ id: 1, triage_acuity: "GREEN", scheduled_for: "2026-09-08T10:00:00Z" }),
      mockAppointment({ id: 2, triage_acuity: "RED", scheduled_for: "2026-09-08T10:15:00Z" }),
      mockAppointment({ id: 3, triage_acuity: "YELLOW", scheduled_for: "2026-09-08T09:30:00Z" }),
      mockAppointment({ id: 4, triage_acuity: "ORANGE", scheduled_for: "2026-09-08T10:10:00Z" }),
      mockAppointment({ id: 5, triage_acuity: null, notes: "Unclassified emergency arrival", scheduled_for: "2026-09-08T10:05:00Z" }),
    ];

    const sorted = [...patients].sort((a, b) => {
      const aTriage = parseTriage(a);
      const bTriage = parseTriage(b);
      const scoreDiff = levelScore[bTriage.level] - levelScore[aTriage.level];
      if (scoreDiff !== 0) return scoreDiff;
      return new Date(a.scheduled_for).getTime() - new Date(b.scheduled_for).getTime();
    });

    const order = sorted.map((p) => parseTriage(p).level);
    // UNTRIAGED (score 5) must be top to prevent clinical neglect
    // then RED (4), ORANGE (3), YELLOW (2), GREEN (1)
    expect(order).toEqual(["UNTRIAGED", "RED", "ORANGE", "YELLOW", "GREEN"]);
  });
});
