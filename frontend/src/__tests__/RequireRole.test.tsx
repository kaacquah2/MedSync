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
import type { CurrentUser } from "@/types";

const mockUseAuth = vi.mocked(useAuth);
type AuthContextType = ReturnType<typeof useAuth>;

function mockAuth(overrides: Partial<AuthContextType> = {}): AuthContextType {
  return {
    user: null,
    loading: false,
    login: vi.fn(),
    logout: vi.fn(),
    refresh: vi.fn(),
    ...overrides,
  };
}

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
    mockUseAuth.mockReturnValue(
      mockAuth({
        user: null,
        loading: true,
      })
    );

    render(
      <RequireRole roles={["doctor"]}>
        <div>protected</div>
      </RequireRole>,
      { wrapper: Wrapper },
    );

    expect(screen.queryByText("protected")).not.toBeInTheDocument();
  });

  it("renders children when the user's role is in the allowed list", () => {
    mockUseAuth.mockReturnValue(
      mockAuth({
        user: { role: "doctor" } as unknown as CurrentUser,
        loading: false,
      })
    );

    render(
      <RequireRole roles={["doctor", "nurse"]}>
        <div>protected content</div>
      </RequireRole>,
      { wrapper: Wrapper },
    );

    expect(screen.getByText("protected content")).toBeInTheDocument();
  });

  it("redirects to /403 when the user role is not in the allowed list", () => {
    mockUseAuth.mockReturnValue(
      mockAuth({
        user: { role: "receptionist" } as unknown as CurrentUser,
        loading: false,
      })
    );

    render(
      <RequireRole roles={["doctor", "nurse"]}>
        <div>protected content</div>
      </RequireRole>,
      { wrapper: Wrapper },
    );

    expect(screen.queryByText("protected content")).not.toBeInTheDocument();
  });
});
