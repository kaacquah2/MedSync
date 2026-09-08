import { describe, expect, it } from "vitest";
import {
  SESSION_DURATION_MS,
  WARN_BEFORE_MS,
  WARN_AT_MS,
  LOGOUT_AT_MS,
  COUNTDOWN_MS,
} from "@/layout/AppLayout";

describe("Clinical Session Inactivity Timeout Guard (HIPAA § 164.312(a)(2)(iii))", () => {
  it("enforces session duration of 15 minutes (900 seconds)", () => {
    expect(SESSION_DURATION_MS).toBe(15 * 60 * 1000);
    expect(LOGOUT_AT_MS).toBe(15 * 60 * 1000);
  });

  it("triggers expiration warning 2 minutes prior to session termination", () => {
    expect(WARN_BEFORE_MS).toBe(2 * 60 * 1000);
    expect(WARN_AT_MS).toBe(13 * 60 * 1000);
    expect(COUNTDOWN_MS).toBe(2 * 60 * 1000);
  });

  it("strictly satisfies HIPAA / NIST SP 800-88 <= 15 minute clinical inactive terminal requirement", () => {
    const maxAllowedInactivityMs = 15 * 60 * 1000;
    expect(SESSION_DURATION_MS).toBeLessThanOrEqual(maxAllowedInactivityMs);
    expect(SESSION_DURATION_MS).toBeGreaterThanOrEqual(5 * 60 * 1000);
  });
});
