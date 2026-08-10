import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { RequireRole } from "@/auth/RequireAuth";

vi.mock("@/auth/AuthProvider", () => ({
  useAuth: vi.fn(),
}));

vi.mock("@/pages/common/AccessDenied", () => ({
  AccessDenied: () => <div data-testid="access-denied">Access Denied</div>,
}));

import { useAuth } from "@/auth/AuthProvider";
const mockUseAuth = vi.mocked(useAuth);

function Wrapper({ children }: { children: React.ReactNode }) {
  return (
    <MantineProvider>
      <MemoryRouter>{children}</MemoryRouter>
    </MantineProvider>
  );
}

describe("RequireRole", () => {
  beforeEach(() => vi.clearAllMocks());

  it("does not render children while auth is loading", () => {
    mockUseAuth.mockReturnValue({
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      user: null, loading: true, logout: vi.fn() as any,
    });

    render(
      <RequireRole roles={["doctor"]}>
        <div>protected</div>
      </RequireRole>,
      { wrapper: Wrapper },
    );

    expect(screen.queryByText("protected")).not.toBeInTheDocument();
  });

  it("renders children when the user's role is in the allowed list", () => {
    mockUseAuth.mockReturnValue({
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      user: { role: "doctor" } as any, loading: false, logout: vi.fn() as any,
    });

    render(
      <RequireRole roles={["doctor", "nurse"]}>
        <div>protected content</div>
      </RequireRole>,
      { wrapper: Wrapper },
    );

    expect(screen.getByText("protected content")).toBeInTheDocument();
  });

  it("redirects to /403 when the user role is not in the allowed list", () => {
    mockUseAuth.mockReturnValue({
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      user: { role: "receptionist" } as any, loading: false, logout: vi.fn() as any,
    });

    render(
      <RequireRole roles={["doctor", "nurse"]}>
        <div>protected content</div>
      </RequireRole>,
      { wrapper: Wrapper },
    );

    expect(screen.queryByText("protected content")).not.toBeInTheDocument();
  });
});
