import { describe, expect, it } from "vitest";
import {
  ROLE_COLORS,
  ROLE_LABELS,
  isRole,
  roleHome,
} from "@/constants/roles";
import { Role } from "@/types";

const ALL_ROLES = [
  "super_admin",
  "hospital_admin",
  "doctor",
  "nurse",
  "lab_technician",
  "receptionist",
] as const;

describe("ROLE_LABELS", () => {
  it("has an entry for every role", () => {
    for (const role of ALL_ROLES) {
      expect(ROLE_LABELS).toHaveProperty(role);
      expect(typeof ROLE_LABELS[role]).toBe("string");
    }
  });

  it("uses title-case display names", () => {
    expect(ROLE_LABELS.super_admin).toBe("Super Admin");
    expect(ROLE_LABELS.lab_technician).toBe("Lab Technician");
  });
});

describe("ROLE_COLORS", () => {
  it("has a colour string for every role", () => {
    for (const role of ALL_ROLES) {
      expect(ROLE_COLORS).toHaveProperty(role);
      expect(typeof ROLE_COLORS[role]).toBe("string");
    }
  });
});

describe("roleHome", () => {
  it("routes super_admin to /superadmin", () => {
    expect(roleHome("super_admin")).toBe("/superadmin");
  });

  it("routes lab_technician to /lab/orders", () => {
    expect(roleHome("lab_technician")).toBe("/lab/orders");
  });

  it("routes receptionist to /receptionist/queue", () => {
    expect(roleHome("receptionist")).toBe("/receptionist/queue");
  });

  it("routes other roles to /", () => {
    const fallbackRoles: Role[] = ["hospital_admin", "doctor", "nurse"];
    for (const role of fallbackRoles) {
      expect(roleHome(role)).toBe("/");
    }
  });
});

describe("isRole", () => {
  it("returns true when the user role is in the allowed list", () => {
    expect(isRole("doctor", "doctor", "nurse")).toBe(true);
  });

  it("returns false when the user role is not in the allowed list", () => {
    expect(isRole("receptionist", "doctor", "nurse")).toBe(false);
  });

  it("returns false for undefined role", () => {
    expect(isRole(undefined, "doctor")).toBe(false);
  });

  it("returns false for empty string role", () => {
    expect(isRole("", "doctor")).toBe(false);
  });
});
