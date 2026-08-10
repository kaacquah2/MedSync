import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AccessDenied } from "@/pages/common/AccessDenied";

vi.mock("@/auth/AuthProvider", () => ({
  useAuth: vi.fn(() => ({
    user: { role: "receptionist", role_display: "Receptionist" },
    loading: false,
    logout: vi.fn(),
  })),
}));

function Wrapper({ children }: { children: React.ReactNode }) {
  return (
    <MantineProvider>
      <MemoryRouter>{children}</MemoryRouter>
    </MantineProvider>
  );
}

describe("AccessDenied (smoke)", () => {
  it("renders without crashing", () => {
    render(<AccessDenied />, { wrapper: Wrapper });
    expect(screen.getByText("Access Denied")).toBeInTheDocument();
  });

  it("shows the user's role display name", () => {
    render(<AccessDenied />, { wrapper: Wrapper });
    expect(screen.getByText(/Receptionist/)).toBeInTheDocument();
  });

  it("shows a back button", () => {
    render(<AccessDenied />, { wrapper: Wrapper });
    expect(screen.getByRole("button", { name: /go back/i })).toBeInTheDocument();
  });
});
