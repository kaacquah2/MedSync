import "@testing-library/jest-dom";
import { render, screen, act } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { useIsPrinting } from "../utils/useIsPrinting";

function DemoPatientChartView({ patientName, nhid }: { patientName: string; nhid: string }) {
  const { isPrinting, triggerPrint } = useIsPrinting();

  return (
    <div>
      <button onClick={triggerPrint}>Print Chart</button>
      <div data-testid="visible-chart">
        <h2>Visible Chart UI</h2>
      </div>
      {isPrinting && (
        <div className="print-only" data-testid="printable-phi-view">
          <h3>{patientName}</h3>
          <p>Universal ID: {nhid}</p>
        </div>
      )}
    </div>
  );
}

describe("Hidden-DOM PHI Leak Prevention", () => {
  const originalPrint = window.print;

  beforeEach(() => {
    window.print = vi.fn();
  });

  afterEach(() => {
    window.print = originalPrint;
  });

  it("does not mount print-only PHI container into the DOM during normal viewing", () => {
    const { container } = render(
      <DemoPatientChartView patientName="Kwame Mensah" nhid="NHID-GHA-12345678" />
    );

    // Visible UI is present
    expect(screen.getByTestId("visible-chart")).toBeInTheDocument();

    // The print-only container MUST NOT exist in the DOM (not even hidden with CSS)
    expect(container.querySelector(".print-only")).toBeNull();
    expect(screen.queryByTestId("printable-phi-view")).toBeNull();
    expect(container.textContent).not.toContain("Universal ID: NHID-GHA-12345678");
  });

  it("dynamically mounts PHI during beforeprint event and unmounts on afterprint", () => {
    const { container } = render(
      <DemoPatientChartView patientName="Kwame Mensah" nhid="NHID-GHA-12345678" />
    );

    expect(container.querySelector(".print-only")).toBeNull();

    // Simulate browser beforeprint event (e.g. Ctrl+P or print menu)
    act(() => {
      window.dispatchEvent(new Event("beforeprint"));
    });

    // Now mounted in the DOM
    expect(container.querySelector(".print-only")).not.toBeNull();
    expect(screen.getByTestId("printable-phi-view")).toBeInTheDocument();
    expect(screen.getByText("Kwame Mensah")).toBeInTheDocument();
    expect(screen.getByText("Universal ID: NHID-GHA-12345678")).toBeInTheDocument();

    // Simulate browser afterprint event (print dialog completed or dismissed)
    act(() => {
      window.dispatchEvent(new Event("afterprint"));
    });

    // Print DOM is purged from the living DOM tree
    expect(container.querySelector(".print-only")).toBeNull();
    expect(screen.queryByTestId("printable-phi-view")).toBeNull();
    expect(container.textContent).not.toContain("Universal ID: NHID-GHA-12345678");
  });

  it("triggerPrint invokes window.print and guarantees cleanup of the DOM node", () => {
    const { container } = render(
      <DemoPatientChartView patientName="Ama Serwaa" nhid="NHID-GHA-87654321" />
    );

    expect(container.querySelector(".print-only")).toBeNull();

    const printButton = screen.getByRole("button", { name: /print chart/i });

    act(() => {
      printButton.click();
    });

    // window.print was called
    expect(window.print).toHaveBeenCalledTimes(1);

    // After print finishes, the DOM is purged
    expect(container.querySelector(".print-only")).toBeNull();
    expect(screen.queryByTestId("printable-phi-view")).toBeNull();
    expect(container.textContent).not.toContain("Universal ID: NHID-GHA-87654321");
  });
});
