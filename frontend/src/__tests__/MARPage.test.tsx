import "@testing-library/jest-dom";
import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { AxiosResponse } from "axios";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { isHighAlertMedication, MARPage } from "../pages/nurse/MARPage";
import * as api from "../api/endpoints";
import type { MedicationAdministration } from "../types";

vi.mock("../api/endpoints", () => ({
  fetchMedAdmins: vi.fn(),
  updateMedAdminStatus: vi.fn(),
}));

const mockFetchMedAdmins = vi.mocked(api.fetchMedAdmins);
const mockUpdateMedAdminStatus = vi.mocked(api.updateMedAdminStatus);

const mockAdmins: MedicationAdministration[] = [
  {
    id: 101,
    prescription: 1,
    prescription_drug_name: "Insulin Actrapid 100IU/ml",
    prescription_dosage: "10 IU",
    prescription_frequency: "TDS",
    patient_name: "Kofi Mensah",
    patient_nhid: "NHID-001",
    bed_label: "Bed 4A",
    administered_by: null,
    administered_by_name: null,
    scheduled_time: "2026-09-08T08:00:00Z",
    administered_time: null,
    status: "due",
    status_display: "Due",
    notes: "",
  },
  {
    id: 102,
    prescription: 2,
    prescription_drug_name: "Morphine Sulfate 10mg",
    prescription_dosage: "10 mg",
    prescription_frequency: "PRN",
    patient_name: "Ama Osei",
    patient_nhid: "NHID-002",
    bed_label: "Bed 2B",
    administered_by: 5,
    administered_by_name: "Nurse Beatrice",
    scheduled_time: "2026-09-08T12:00:00Z",
    administered_time: "2026-09-08T12:05:00Z",
    status: "given",
    status_display: "Given",
    notes: "Given with water",
  },
  {
    id: 103,
    prescription: 3,
    prescription_drug_name: "Amoxicillin 500mg",
    prescription_dosage: "500 mg",
    prescription_frequency: "TDS",
    patient_name: "Kwame Nkrumah",
    patient_nhid: "NHID-003",
    bed_label: "Bed 1A",
    administered_by: null,
    administered_by_name: null,
    scheduled_time: "2026-09-08T09:30:00Z", // Same 08:00 morning slot window
    administered_time: null,
    status: "due",
    status_display: "Due",
    notes: "",
  },
  {
    id: 104,
    prescription: 3,
    prescription_drug_name: "Amoxicillin 500mg",
    prescription_dosage: "500 mg",
    prescription_frequency: "TDS",
    patient_name: "Kwame Nkrumah",
    patient_nhid: "NHID-003",
    bed_label: "Bed 1A",
    administered_by: null,
    administered_by_name: null,
    scheduled_time: "2026-09-08T08:00:00Z", // Standard 08:00 slot
    administered_time: null,
    status: "due",
    status_display: "Due",
    notes: "",
  },
];

function renderWithClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });

  return render(
    <MantineProvider>
      <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
    </MantineProvider>
  );
}

describe("isHighAlertMedication helper", () => {
  it("identifies high-alert medications correctly", () => {
    expect(isHighAlertMedication("Insulin Actrapid 100IU/ml")).toBe(true);
    expect(isHighAlertMedication("Insulin Mixtard 30/70")).toBe(true);
    expect(isHighAlertMedication("Morphine Sulfate 10mg")).toBe(true);
    expect(isHighAlertMedication("Heparin Sodium 5,000 units")).toBe(true);
    expect(isHighAlertMedication("Enoxaparin 40mg")).toBe(true);
    expect(isHighAlertMedication("Potassium Chloride 20mEq")).toBe(true);
    expect(isHighAlertMedication("Digoxin 0.25mg")).toBe(true);
    expect(isHighAlertMedication("Methotrexate 2.5mg")).toBe(true);
    expect(isHighAlertMedication("Fentanyl Patch 25mcg")).toBe(true);
  });

  it("identifies non-high-alert medications correctly", () => {
    expect(isHighAlertMedication("Paracetamol 500mg")).toBe(false);
    expect(isHighAlertMedication("Amoxicillin 500mg")).toBe(false);
    expect(isHighAlertMedication("Omeprazole 20mg")).toBe(false);
    expect(isHighAlertMedication("Metformin 500mg")).toBe(false);
  });
});

describe("MARPage Safety Confirmations", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetchMedAdmins.mockResolvedValue({ data: mockAdmins } as AxiosResponse<MedicationAdministration[]>);
    mockUpdateMedAdminStatus.mockResolvedValue({ data: {} as MedicationAdministration } as AxiosResponse<MedicationAdministration>);
  });

  it("renders pending and given doses and indicates high-alert medication", async () => {
    renderWithClient(<MARPage />);

    expect(await screen.findByText("Kofi Mensah")).toBeInTheDocument();
    expect(screen.getByText("Ama Osei")).toBeInTheDocument();

    // High alert badge rendered for Insulin and Morphine
    const highAlertBadges = screen.getAllByText("HIGH-ALERT");
    expect(highAlertBadges.length).toBeGreaterThanOrEqual(2);
  });

  it("prevents slot collision by rendering multiple doses scheduled in the same time window", async () => {
    renderWithClient(<MARPage />);

    // Kwame Nkrumah has two Amoxicillin doses in morning window: 08:00 and 09:30
    expect(await screen.findByText("Kwame Nkrumah")).toBeInTheDocument();
    // Both doses should be present (one standard, one with 09:30 label)
    expect(screen.getByText("09:30")).toBeInTheDocument();
  });

  it("opens administration modal when clicking due dose, blocks without PIN, and calls update when PIN provided", async () => {
    renderWithClient(<MARPage />);

    const administerBtn = await screen.findByRole("button", {
      name: /Administer Insulin Actrapid 100IU\/ml for Kofi Mensah/i,
    });

    // Clicking does NOT instantly toggle the dose
    fireEvent.click(administerBtn);
    expect(mockUpdateMedAdminStatus).not.toHaveBeenCalled();

    // Administration confirmation modal opens with high-alert safeguard warning
    expect(await screen.findByText("Confirm Medication Administration")).toBeInTheDocument();
    expect(screen.getByText("HIGH-ALERT MEDICATION SAFEGUARD")).toBeInTheDocument();
    expect(screen.getByText(/5 Rights/)).toBeInTheDocument();

    const confirmBtn = screen.getByRole("button", { name: "Confirm Administration" });
    expect(confirmBtn).toBeDisabled();

    // Enter 4-digit PIN in the inputs
    const pinInputs = document.querySelectorAll<HTMLInputElement>('input[type="password"]');
    expect(pinInputs.length).toBeGreaterThanOrEqual(4);

    fireEvent.change(pinInputs[0], { target: { value: "1" } });
    fireEvent.change(pinInputs[1], { target: { value: "2" } });
    fireEvent.change(pinInputs[2], { target: { value: "3" } });
    fireEvent.change(pinInputs[3], { target: { value: "4" } });

    await waitFor(() => {
      expect(confirmBtn).not.toBeDisabled();
    });

    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(mockUpdateMedAdminStatus).toHaveBeenCalledWith(101, "given", undefined);
    });
  });

  it("opens reversal warning modal when clicking given dose, warns about double dosing, requires justification and PIN", async () => {
    renderWithClient(<MARPage />);

    const givenBtn = await screen.findByRole("button", {
      name: /Given dose Morphine Sulfate 10mg for Ama Osei/i,
    });

    // Clicking does NOT instantly revert to due
    fireEvent.click(givenBtn);
    expect(mockUpdateMedAdminStatus).not.toHaveBeenCalled();

    // Critical reversal modal opens with double-dosing danger alert
    expect(await screen.findByText("Reverse Medication Administration (High Risk)")).toBeInTheDocument();
    expect(screen.getByText("CRITICAL SAFETY HAZARD: Potential Double-Dosing")).toBeInTheDocument();

    const reverseBtn = screen.getByRole("button", { name: "Confirm Reversal to Due" });
    expect(reverseBtn).toBeDisabled();

    // Select reason
    const reasonInput = screen.getByPlaceholderText("Select clinical reason for reversal");
    fireEvent.change(reasonInput, {
      target: { value: "Entered in error (documentation mistake)" },
    });
    fireEvent.click(reasonInput);

    // Enter detailed justification (>=10 chars)
    const justificationInput = screen.getByLabelText(/Detailed Clinical Justification/i);
    fireEvent.change(justificationInput, {
      target: { value: "Dose was documented under wrong patient; verified with Ward Sister." },
    });

    // Still disabled without PIN
    expect(reverseBtn).toBeDisabled();

    // Reversal PIN inputs
    const pinInputs = document.querySelectorAll<HTMLInputElement>('input[type="password"]');
    expect(pinInputs.length).toBeGreaterThanOrEqual(4);
    fireEvent.change(pinInputs[0], { target: { value: "9" } });
    fireEvent.change(pinInputs[1], { target: { value: "8" } });
    fireEvent.change(pinInputs[2], { target: { value: "7" } });
    fireEvent.change(pinInputs[3], { target: { value: "6" } });

    // Cancel closes modal without calling API
    const cancelBtn = screen.getByRole("button", { name: "Keep as Given (Cancel)" });
    fireEvent.click(cancelBtn);

    expect(mockUpdateMedAdminStatus).not.toHaveBeenCalled();
    expect(screen.queryByText("Reverse Medication Administration (High Risk)")).not.toBeInTheDocument();
  });
});
