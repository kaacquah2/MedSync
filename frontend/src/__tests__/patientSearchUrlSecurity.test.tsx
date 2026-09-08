import "@testing-library/jest-dom";
import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation, type MemoryRouterProps } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PatientSearchPage } from "../pages/patients/PatientSearchPage";
import * as api from "../api/endpoints";

vi.mock("@/auth/AuthProvider", () => ({
  useAuth: vi.fn(() => ({
    user: { id: "user-1", role: "doctor", hospital: { id: "hosp-1" } },
    loading: false,
  })),
}));

vi.mock("../api/endpoints", () => ({
  searchPatients: vi.fn(),
}));

const mockSearchPatients = vi.mocked(api.searchPatients);

function LocationTracker() {
  const location = useLocation();
  return (
    <div data-testid="location-display">
      <span data-testid="pathname">{location.pathname}</span>
      <span data-testid="search">{location.search}</span>
    </div>
  );
}

function renderPatientSearch(
  initialEntries: MemoryRouterProps["initialEntries"] = ["/patients"]
) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });

  return render(
    <MantineProvider>
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={initialEntries}>
          <LocationTracker />
          <PatientSearchPage />
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>
  );
}

describe("Patient Identifiers in URL Query Strings Prevention", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockSearchPatients.mockResolvedValue({
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      data: { count: 0, next: null, previous: null, results: [] } as any,
      status: 200,
      statusText: "OK",
      headers: {},
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      config: {} as any,
    });
  });

  it("does not serialize search query into URL search params when searching", async () => {
    renderPatientSearch(["/patients"]);

    const searchInput = screen.getByPlaceholderText(/Search by name, NHID, or national ID/i);

    fireEvent.change(searchInput, { target: { value: "Kwame Mensah" } });
    fireEvent.submit(searchInput.closest("form")!);

    await waitFor(() => {
      expect(mockSearchPatients).toHaveBeenCalledWith("Kwame Mensah", 1);
    });

    // The URL query string MUST NOT contain the patient name
    const searchSpan = screen.getByTestId("search");
    expect(searchSpan.textContent).toBe("");
    expect(searchSpan.textContent).not.toContain("Kwame");
  });

  it("reads query passed via navigation state without placing it in the URL", async () => {
    const initialEntry = {
      pathname: "/patients",
      state: { q: "GHA-712345678-9" },
    };

    renderPatientSearch([initialEntry]);

    await waitFor(() => {
      expect(mockSearchPatients).toHaveBeenCalledWith("GHA-712345678-9", 1);
    });

    // National ID must NOT be present in the URL query string
    const searchSpan = screen.getByTestId("search");
    expect(searchSpan.textContent).toBe("");
  });

  it("sanitizes incoming URL search query strings and purges them from the address bar", async () => {
    renderPatientSearch(["/patients?q=SensitivePatientName"]);

    await waitFor(() => {
      // The search query string should be stripped from the URL
      const searchSpan = screen.getByTestId("search");
      expect(searchSpan.textContent).toBe("");
    });
  });
});
