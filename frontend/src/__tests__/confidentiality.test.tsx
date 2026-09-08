import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";
import { MantineProvider } from "@mantine/core";
import { ConfidentialityBadge } from "../components/ConfidentialityBadge";

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <MantineProvider>{children}</MantineProvider>
);

describe("ConfidentialityBadge Component", () => {
  it("renders nothing for normal confidentiality when showNormal is false", () => {
    render(<ConfidentialityBadge level="normal" />, { wrapper });
    expect(screen.queryByText("Standard")).toBeNull();
    expect(screen.queryByText("Restricted")).toBeNull();
    expect(screen.queryByText("Very Restricted")).toBeNull();
  });

  it("renders standard badge when showNormal is true", () => {
    render(<ConfidentialityBadge level="normal" showNormal />, { wrapper });
    expect(screen.getByText("Standard")).toBeDefined();
  });

  it("renders Restricted badge with shield icon for restricted tier", () => {
    render(<ConfidentialityBadge level="restricted" />, { wrapper });
    const badge = screen.getByText("Restricted");
    expect(badge).toBeDefined();
  });

  it("renders Very Restricted badge for very_restricted tier", () => {
    render(<ConfidentialityBadge level="very_restricted" />, { wrapper });
    const badge = screen.getByText("Very Restricted");
    expect(badge).toBeDefined();
  });
});
