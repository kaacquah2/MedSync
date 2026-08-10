/**
 * Single source-of-truth for role values, labels, colours, and helpers.
 * All components should import from here — never hardcode "DOCTOR" etc.
 */

import type { Role } from "@/types";

export const ROLE_LABELS: Record<Role, string> = {
  super_admin:    "Super Admin",
  hospital_admin: "Hospital Admin",
  doctor:         "Doctor",
  nurse:          "Nurse",
  lab_technician: "Lab Technician",
  receptionist:   "Receptionist",
};

export const ROLE_COLORS: Record<Role, string> = {
  super_admin:    "red",
  hospital_admin: "orange",
  doctor:         "blue",
  nurse:          "teal",
  lab_technician: "violet",
  receptionist:   "gray",
};

/** Landing route for a given role after login. */
export function roleHome(role: Role): string {
  switch (role) {
    case "super_admin":
      return "/superadmin";
    case "hospital_admin":
      // TODO: No separate admin console route exists, fallback to default dashboard at "/"
      return "/";
    case "doctor":
      // TODO: No separate clinical dashboard (patient list / consultations) route exists, fallback to default dashboard at "/"
      return "/";
    case "nurse":
      // TODO: No separate ward view / vitals queue route exists, fallback to default dashboard at "/"
      return "/";
    case "lab_technician":
      return "/lab/orders";
    case "receptionist":
      return "/receptionist/queue";
    default:
      return "/";
  }
}

/** Returns true if userRole is one of the given roles. */
export function isRole(userRole: string | undefined, ...roles: Role[]): boolean {
  if (!userRole) return false;
  return (roles as string[]).includes(userRole);
}
