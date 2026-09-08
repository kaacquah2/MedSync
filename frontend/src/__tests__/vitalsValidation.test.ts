import { describe, expect, it } from "vitest";
import {
  PHYSIOLOGICAL_BOUNDS,
  validateVitalsForm,
  type VitalsFormValues,
} from "../pages/vitals/VitalsPage";

describe("Vital Signs Validation — Hard Physiological Boundaries", () => {
  const emptyForm: VitalsFormValues = {
    bp_systolic: undefined,
    bp_diastolic: undefined,
    temperature: undefined,
    heart_rate: undefined,
    respiratory_rate: undefined,
    spo2: undefined,
    weight_kg: undefined,
    pain_score: undefined,
  };

  it("rejects catastrophic out-of-bounds temperature (999.9°C and 25°C)", () => {
    const errorsHigh = validateVitalsForm({ ...emptyForm, temperature: 999.9 });
    expect(errorsHigh.temperature).toBeDefined();
    expect(errorsHigh.temperature).toContain("Temperature must be between 30 and 45 °C");

    const errorsLow = validateVitalsForm({ ...emptyForm, temperature: 25.0 });
    expect(errorsLow.temperature).toBeDefined();
    expect(errorsLow.temperature).toContain("Temperature must be between 30 and 45 °C");
  });

  it("rejects catastrophic out-of-bounds pain score (500)", () => {
    const errors = validateVitalsForm({ ...emptyForm, pain_score: 500 });
    expect(errors.pain_score).toBeDefined();
    expect(errors.pain_score).toContain("Pain Score must be between 0 and 10");

    const errorsNegative = validateVitalsForm({ ...emptyForm, pain_score: -1 });
    expect(errorsNegative.pain_score).toBeDefined();
  });

  it("rejects blood pressure where systolic is less than or equal to diastolic", () => {
    // Systolic < Diastolic (e.g. 80 / 120)
    const errorsInverted = validateVitalsForm({
      ...emptyForm,
      bp_systolic: 80,
      bp_diastolic: 120,
    });
    expect(errorsInverted.bp_systolic).toBe(
      "Systolic blood pressure must be greater than diastolic blood pressure."
    );

    // Systolic == Diastolic (e.g. 100 / 100)
    const errorsEqual = validateVitalsForm({
      ...emptyForm,
      bp_systolic: 100,
      bp_diastolic: 100,
    });
    expect(errorsEqual.bp_systolic).toBe(
      "Systolic blood pressure must be greater than diastolic blood pressure."
    );
  });

  it("rejects out-of-bounds heart rate (< 20 or > 300 bpm)", () => {
    expect(validateVitalsForm({ ...emptyForm, heart_rate: 15 }).heart_rate).toContain(
      "Heart Rate must be between 20 and 300 bpm"
    );
    expect(validateVitalsForm({ ...emptyForm, heart_rate: 350 }).heart_rate).toContain(
      "Heart Rate must be between 20 and 300 bpm"
    );
  });

  it("rejects out-of-bounds SpO2 (< 50% or > 100%)", () => {
    expect(validateVitalsForm({ ...emptyForm, spo2: 45 }).spo2).toContain(
      "SpO₂ must be between 50 and 100 %"
    );
    expect(validateVitalsForm({ ...emptyForm, spo2: 105 }).spo2).toContain(
      "SpO₂ must be between 50 and 100 %"
    );
  });

  it("rejects out-of-bounds respiratory rate (< 4 or > 80 br/min)", () => {
    expect(validateVitalsForm({ ...emptyForm, respiratory_rate: 2 }).respiratory_rate).toContain(
      "Respiratory Rate must be between 4 and 80 br/min"
    );
    expect(validateVitalsForm({ ...emptyForm, respiratory_rate: 95 }).respiratory_rate).toContain(
      "Respiratory Rate must be between 4 and 80 br/min"
    );
  });

  it("accepts valid physiological values and boundaries", () => {
    const validNormal: VitalsFormValues = {
      bp_systolic: 120,
      bp_diastolic: 80,
      temperature: 36.8,
      heart_rate: 72,
      respiratory_rate: 16,
      spo2: 98,
      weight_kg: 70.5,
      pain_score: 2,
    };
    const errors = validateVitalsForm(validNormal);
    expect(Object.keys(errors)).toHaveLength(0);

    // Hard boundary edge cases
    const boundaryValid: VitalsFormValues = {
      bp_systolic: PHYSIOLOGICAL_BOUNDS.bp_systolic.max,
      bp_diastolic: PHYSIOLOGICAL_BOUNDS.bp_diastolic.min,
      temperature: PHYSIOLOGICAL_BOUNDS.temperature.max,
      heart_rate: PHYSIOLOGICAL_BOUNDS.heart_rate.max,
      respiratory_rate: PHYSIOLOGICAL_BOUNDS.respiratory_rate.max,
      spo2: PHYSIOLOGICAL_BOUNDS.spo2.max,
      weight_kg: PHYSIOLOGICAL_BOUNDS.weight_kg.max,
      pain_score: PHYSIOLOGICAL_BOUNDS.pain_score.max,
    };
    const boundaryErrors = validateVitalsForm(boundaryValid);
    expect(Object.keys(boundaryErrors)).toHaveLength(0);
  });
});
