/**
 * Query key factory for consistent, scoped React Query keys.
 * Keys are scoped with hospital_id and user_id to prevent stale cross-session data leaks.
 */

export const queryKeys = {
  scoped: (hospitalId?: string | number | null, userId?: string | number | null, key?: string | unknown[]) => {
    const scope = [hospitalId ?? "no-hosp", userId ?? "no-user"];
    if (!key) return scope;
    return Array.isArray(key) ? [...scope, ...key] : [...scope, key];
  },
  patients: (hospitalId?: string | number | null, userId?: string | number | null, search = "", page = 1) =>
    queryKeys.scoped(hospitalId, userId, ["patients", search, page]),
  patientDetail: (hospitalId?: string | number | null, userId?: string | number | null, nhid = "") =>
    queryKeys.scoped(hospitalId, userId, ["patient-detail", nhid]),
  worklist: (hospitalId?: string | number | null, userId?: string | number | null) =>
    queryKeys.scoped(hospitalId, userId, ["worklist"]),
  vitals: (hospitalId?: string | number | null, userId?: string | number | null, nhid = "") =>
    queryKeys.scoped(hospitalId, userId, ["vitals", nhid]),
  labOrders: (hospitalId?: string | number | null, userId?: string | number | null) =>
    queryKeys.scoped(hospitalId, userId, ["lab-orders"]),
  dashboard: (hospitalId?: string | number | null, userId?: string | number | null) =>
    queryKeys.scoped(hospitalId, userId, ["dashboard"]),
};
