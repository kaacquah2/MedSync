/**
 * Typed API endpoint helpers wrapping the Axios client.
 * Each function maps 1-to-1 with an /api/* URL.
 */

import api from "./client";
import type {
  AIQueryResult,
  AccessDecision,
  AlertsFeed,
  Appointment,
  AuditLogEntry,
  ChainValidation,
  CurrentUser,
  DashboardData,
  Encounter,
  EncounterSummary,
  Handover,
  Hospital,
  LabOrder,
  MfaStatus,
  Paginated,
  Patient,
  PatientAlert,
  PatientDocument,
  PatientRecordsSummary,
  PatientSummary,
  Referral,
  ShiftRecord,
  Staff,
  VitalSign,
  Ward,
  MedicationAdministration,
} from "@/types";

// ── CSRF ─────────────────────────────────────────────────────────────────────

export const fetchCsrf = () => api.get("/csrf/");

// ── Health-check ──────────────────────────────────────────────────────────────

export const fetchHealthz = () =>
  api.get<{ status: string; database: string; encryption: string }>("/healthz/", { baseURL: "" }).then((r) => r.data);

// ── Auth ──────────────────────────────────────────────────────────────────────

export const fetchMe = () => api.get<CurrentUser>("/me/");
export const updateMe = (data: Partial<CurrentUser>) => api.patch<CurrentUser>("/me/", data);

export const login = (username: string, password: string) =>
  api.post<CurrentUser>("/auth/login/", { username, password });

export const logout = () => api.post("/auth/logout/");

export const changePassword = (old_password: string, new_password: string) =>
  api.post("/auth/password/change/", { old_password, new_password });

// ── MFA ───────────────────────────────────────────────────────────────────────

export const fetchMfaStatus = () => api.get<MfaStatus>("/mfa/status/");

export const getMfaSetup = () =>
  api.get<{ qr_code: string; uri: string; secret: string }>("/mfa/setup/");

export const confirmMfaSetup = (code: string) =>
  api.post<{ detail: string; recovery_codes: string[] }>("/mfa/setup/", { code });

export const verifyMfa = (code: string) => api.post("/mfa/verify/", { code });

export const sendEmailOtp = () =>
  api.post<{ detail: string; email_masked: string }>("/mfa/send-email-otp/");

export const disableMfa = (code: string) => api.post("/mfa/disable/", { code });

export const regenerateCodes = (code: string) =>
  api.post<{ recovery_codes: string[] }>("/mfa/regenerate-codes/", { code });

export const signoutAll = () => api.post("/security/signout-all/");

// ── Dashboard ─────────────────────────────────────────────────────────────────

export const fetchDashboard = () => api.get<DashboardData>("/dashboard/");

// ── Patients ──────────────────────────────────────────────────────────────────

export const searchPatients = (q: string, page = 1) =>
  api.get<Paginated<PatientSummary>>(`/patients/?q=${encodeURIComponent(q)}&page=${page}`);

export const createPatient = (data: Record<string, unknown>, confirm_new?: boolean) =>
  api.post<Patient>("/patients/new/", { ...data, confirm_new });

export const fetchPatient = (nhid: string) => api.get<Patient>(`/patients/${nhid}/`);

export const updatePatient = (nhid: string, data: Partial<Patient>) =>
  api.patch<Patient>(`/patients/${nhid}/`, data);

export const checkPatientAccess = (nhid: string) =>
  api.get<AccessDecision>(`/patients/${nhid}/access/`);

export const breakGlass = (nhid: string, reason: string, code?: string) =>
  api.post(`/patients/${nhid}/break-glass/`, { reason, ...(code ? { code } : {}) });

// ── Encounters ────────────────────────────────────────────────────────────────

export const fetchPatientEncounters = (nhid: string) =>
  api.get<EncounterSummary[]>(`/patients/${nhid}/encounters/`);

export const createEncounter = (
  nhid: string,
  data: { encounter_type: string; chief_complaint: string; notes?: string }
) => api.post<Encounter>(`/patients/${nhid}/encounters/`, data);

export const fetchEncounter = (id: number) => api.get<Encounter>(`/encounters/${id}/`);

// ── Clinical records ──────────────────────────────────────────────────────────

export const createDiagnosis = (
  encounterId: number,
  data: { icd_code?: string; snomed_code?: string; description: string; is_primary?: boolean }
) => api.post(`/encounters/${encounterId}/diagnoses/`, data);

export const createPrescription = (
  encounterId: number,
  data: {
    drug_name: string;
    rxnorm_code?: string;
    dosage: string;
    frequency: string;
    instructions?: string;
  }
) => api.post(`/encounters/${encounterId}/prescriptions/`, data);

export const createLabResult = (
  encounterId: number,
  data: {
    test_name: string;
    loinc_code?: string;
    result_value: string;
    reference_range?: string;
    is_abnormal?: boolean;
    performed_at?: string;
  }
) => api.post(`/encounters/${encounterId}/lab-results/`, data);

// ── Patient alerts ────────────────────────────────────────────────────────────

export const createAlert = (nhid: string, data: Partial<PatientAlert>) =>
  api.post<PatientAlert>(`/patients/${nhid}/alerts/`, data);

export const deactivateAlert = (nhid: string, alertId: number) =>
  api.post(`/patients/${nhid}/alerts/${alertId}/deactivate/`);

// ── Staff ─────────────────────────────────────────────────────────────────────

export const fetchStaff = (params?: Record<string, string>) =>
  api.get<Paginated<Staff>>("/staff/", { params });

export const fetchStaffMember = (id: number) => api.get<Staff>(`/staff/${id}/`);

export const createStaff = (data: Record<string, unknown>) =>
  api.post<Staff>("/staff/", data);

export const updateStaff = (id: number, data: Partial<Staff>) =>
  api.patch<Staff>(`/staff/${id}/`, data);

export const setStaffActive = (id: number, is_active: boolean) =>
  api.post(`/staff/${id}/set-active/`, { is_active });

export const resetStaffPassword = (id: number, password: string) =>
  api.post<{ detail: string }>(`/staff/${id}/reset-password/`, { password });

// ── Hospitals ─────────────────────────────────────────────────────────────────

export const fetchHospitals = () => api.get<Paginated<Hospital>>("/hospitals/");

export const fetchHospital = (id: number) => api.get<Hospital>(`/hospitals/${id}/`);

export const createHospital = (data: Partial<Hospital>) =>
  api.post<Hospital>("/hospitals/", data);

export const updateHospital = (id: number, data: Partial<Hospital>) =>
  api.patch<Hospital>(`/hospitals/${id}/`, data);

// ── Audit log ─────────────────────────────────────────────────────────────────

export const fetchAuditLog = (params?: Record<string, string>) =>
  api.get<Paginated<AuditLogEntry>>("/audit/", { params });

export const fetchAuditActions = () =>
  api.get<{ value: string; label: string }[]>("/audit/actions/");

export const validateAuditChain = () =>
  api.post<ChainValidation>("/audit/validate-chain/");

// ── Alerts feed ───────────────────────────────────────────────────────────────

export const fetchAlerts = () => api.get<AlertsFeed>("/alerts/");

// ── AI query ─────────────────────────────────────────────────────────────────

export const queryPatientAI = (nhid: string, question: string) =>
  api.post<AIQueryResult>(`/patients/${nhid}/ai-query/`, { question });

// ── Patient chart records summary ─────────────────────────────────────────────

export const fetchPatientRecords = (nhid: string) =>
  api.get<PatientRecordsSummary>(`/patients/${nhid}/records-summary/`);

// ── Patient documents ─────────────────────────────────────────────────────────

export const fetchPatientDocuments = (nhid: string) =>
  api.get<PatientDocument[]>(`/patients/${nhid}/documents/`);

export const uploadPatientDocument = (nhid: string, file: File, description?: string) => {
  const form = new FormData();
  form.append("file", file);
  if (description) form.append("description", description);
  return api.post<PatientDocument>(`/patients/${nhid}/documents/`, form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
};

export const deletePatientDocument = (nhid: string, docId: number) =>
  api.delete(`/patients/${nhid}/documents/${docId}/`);

// ── Vitals ────────────────────────────────────────────────────────────────────

export const fetchPatientVitals = (nhid: string) =>
  api.get<VitalSign[]>(`/patients/${nhid}/vitals/`);

export const createVitalSign = (nhid: string, data: Partial<VitalSign>) =>
  api.post<VitalSign>(`/patients/${nhid}/vitals/`, data);

// ── Lab orders ────────────────────────────────────────────────────────────────

export const fetchPatientLabOrders = (nhid: string) =>
  api.get<LabOrder[]>(`/patients/${nhid}/lab-orders/`);

export const createLabOrder = (nhid: string, data: Partial<LabOrder>) =>
  api.post<LabOrder>(`/patients/${nhid}/lab-orders/`, data);

export const fetchLabWorklist = () => api.get<LabOrder[]>("/lab-orders/worklist/");

export const updateLabOrderStatus = (id: number, status: LabOrder["status"]) =>
  api.patch<LabOrder>(`/lab-orders/${id}/status/`, { status });

// ── Appointments ──────────────────────────────────────────────────────────────

export const fetchAppointments = (params?: Record<string, string>) =>
  api.get<Appointment[]>("/appointments/", { params });

export const createAppointment = (data: Partial<Appointment>) =>
  api.post<Appointment>("/appointments/", data);

export const updateAppointment = (id: number, data: Partial<Appointment>) =>
  api.patch<Appointment>(`/appointments/${id}/`, data);

export const appointmentAction = (id: number, action: string) =>
  api.post<Appointment>(`/appointments/${id}/status/`, { action });

// ── Referrals ─────────────────────────────────────────────────────────────────

export const fetchReferrals = (params?: Record<string, string>) =>
  api.get<Paginated<Referral>>("/referrals/", { params });

export const createReferral = (data: Partial<Referral> & { patient_nhid?: string }) =>
  api.post<Referral>("/referrals/", data);

export const updateReferralStatus = (id: number, status: string, notes?: string) =>
  api.patch<Referral>(`/referrals/${id}/status/`, { status, status_notes: notes });

// ── Wards & Beds ──────────────────────────────────────────────────────────────

export const fetchWards = (params?: Record<string, string>) =>
  api.get<Ward[]>("/wards/", { params });

export const createWard = (data: Partial<Ward>) =>
  api.post<Ward>("/wards/", data);

export const updateBedStatus = (id: number, status: string) =>
  api.patch(`/beds/${id}/status/`, { status });

// ── Shifts & Handovers ────────────────────────────────────────────────────────

export const fetchShifts = () => api.get<ShiftRecord[]>("/shifts/");

export const startShift = (data: { ward?: number }) =>
  api.post<ShiftRecord>("/shifts/start/", data);

export const endShift = (id: number, break_minutes?: number) =>
  api.patch<ShiftRecord>(`/shifts/${id}/end/`, { break_minutes });

export const fetchHandovers = () => api.get<Handover[]>("/handovers/");

export const createHandover = (data: Partial<Handover>) =>
  api.post<Handover>("/handovers/", data);

export const acknowledgeHandover = (id: number) =>
  api.patch<Handover>(`/handovers/${id}/acknowledge/`);

// ── Real-Time Sync Endpoints ──────────────────────────────────────────────────

export const reviewAuditLog = (id: number) =>
  api.post(`/audit/${id}/review/`);

export const unreviewAuditLog = (id: number) =>
  api.delete(`/audit/${id}/review/`);

export const fetchMedAdmins = (params?: Record<string, string>) =>
  api.get<MedicationAdministration[]>("/med-admins/", { params });

export const updateMedAdminStatus = (id: number, status: string, notes?: string) =>
  api.patch<MedicationAdministration>(`/med-admins/${id}/status/`, { status, notes });

