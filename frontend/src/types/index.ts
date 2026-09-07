// ── Domain types mirroring the Django models ─────────────────────────────────

export type Role =
  | "super_admin"
  | "hospital_admin"
  | "doctor"
  | "nurse"
  | "lab_technician"
  | "receptionist";

export interface Hospital {
  id: number;
  name: string;
  code: string;
  address?: string;
  city?: string;
  country?: string;
  phone?: string;
  email?: string;
  website?: string;
  is_active: boolean;
  created_at?: string;
}

export interface HospitalMinimal {
  id: number;
  name: string;
  code: string;
}

export interface CurrentUser {
  id: number;
  username: string;
  first_name: string;
  last_name: string;
  full_name: string;
  email: string;
  role: Role;
  role_display: string;
  hospital: HospitalMinimal | null;
  is_clinical: boolean;
  is_admin_level: boolean;
  mfa_enabled: boolean;
  recovery_codes_count: number;
  phone?: string;
  bio?: string;
  date_joined: string;
}

export interface Staff {
  id: number;
  username: string;
  first_name: string;
  last_name: string;
  full_name: string;
  email: string;
  role: Role;
  role_display: string;
  hospital: HospitalMinimal | null;
  phone?: string;
  bio?: string;
  is_active: boolean;
  is_clinical: boolean;
  mfa_enabled: boolean;
  date_joined: string;
}

export interface PatientSummary {
  universal_id: string;
  full_name: string | null;
  first_name?: string | null;
  last_name?: string | null;
  date_of_birth?: string | null;
  sex?: string | null;
  blood_group?: string | null;
  registered_at_hospital: HospitalMinimal | null;
  created_at?: string | null;
  has_access?: boolean;
}

export interface Patient extends Omit<PatientSummary, "full_name" | "first_name" | "last_name" | "date_of_birth" | "sex" | "blood_group" | "created_at"> {
  full_name: string;
  first_name: string;
  last_name: string;
  date_of_birth: string;
  sex: string;
  blood_group: string;
  created_at: string;
  national_id?: string;
  phone?: string;
  email?: string;
  address?: string;
  sex_display: string;
  blood_group_display: string;
  registered_by: { id: number; username: string; full_name: string } | null;
  active_alerts_count: number;
  updated_at: string;
  alerts: PatientAlert[];
  access_basis?: string;
  is_cross_hospital?: boolean;
}

export interface PatientAlert {
  id: number;
  kind: "ALLERGY" | "ALERT";
  kind_display: string;
  label: string;
  severity: "MILD" | "MODERATE" | "SEVERE" | "LIFE_THREAT";
  severity_display: string;
  reaction?: string;
  recorded_by: { id: number; full_name: string } | null;
  recorded_at_hospital: HospitalMinimal | null;
  is_active: boolean;
  is_high_risk: boolean;
  created_at: string;
}

export interface Diagnosis {
  id: number;
  icd_code?: string;
  snomed_code?: string;
  description: string;
  is_primary: boolean;
  created_by: { id: number; full_name: string } | null;
  created_at: string;
}

export interface Prescription {
  id: number;
  drug_name: string;
  rxnorm_code?: string;
  dosage: string;
  frequency: string;
  instructions?: string;
  created_by: { id: number; full_name: string } | null;
  created_at: string;
}

export interface LabResult {
  id: number;
  test_name: string;
  loinc_code?: string;
  result_value: string;
  reference_range?: string;
  is_abnormal: boolean;
  performed_at?: string;
  created_by: { id: number; full_name: string } | null;
  patient_nhid?: string;
  created_at: string;
}

export interface Encounter {
  id: number;
  encounter_type: string;
  encounter_type_display: string;
  chief_complaint: string;
  notes?: string;
  created_by: { id: number; full_name: string; role: Role } | null;
  created_at_hospital: HospitalMinimal | null;
  patient_nhid: string;
  patient_name: string;
  is_cross_hospital: boolean;
  has_abnormal_labs?: boolean;
  diagnoses: Diagnosis[];
  prescriptions: Prescription[];
  lab_results: LabResult[];
  created_at: string;
  updated_at: string;
  can_prescribe?: boolean;
  can_add_lab?: boolean;
  can_diagnose?: boolean;
}

export interface EncounterSummary {
  id: number;
  encounter_type: string;
  encounter_type_display: string;
  created_by: { id: number; full_name: string } | null;
  created_at_hospital: HospitalMinimal | null;
  patient_nhid: string;
  patient_name: string;
  is_cross_hospital: boolean;
  has_abnormal_labs: boolean;
  created_at: string;
}

export interface AuditLogEntry {
  id: number;
  actor_username: string;
  actor_role: string;
  actor_hospital: string;
  action: string;
  action_display: string;
  timestamp: string;
  target_type: string;
  target_id: string;
  patient_nhid: string;
  is_cross_hospital: boolean;
  ip_address: string | null;
  extra: Record<string, unknown>;
  is_reviewed?: boolean;
}

// ── Dashboard types ───────────────────────────────────────────────────────────

export interface StatCard {
  value: string | number;
  label: string;
  icon?: string;
  color: string;
  link?: string;
  delta?: string;       // e.g. "+2 today", "↑ 3 this week"
  delta_color?: string; // "green" | "red" | "dimmed"
}

export interface ChartDataset {
  label?: string;
  data: number[];
  color?: string;
  colors?: string[];
}

export interface ChartConfig {
  type: "line" | "bar" | "doughnut" | "horizontal-bar";
  labels: string[];
  datasets: ChartDataset[];
}

export interface DashboardData {
  role: Role;
  stats: StatCard[];
  charts: Record<string, ChartConfig>;
  recent_encounters?: EncounterSummary[];
  recent_audits?: AuditLogEntry[];
  recent_labs?: LabResult[];
}

// ── Phase B — new clinical domain types ──────────────────────────────────────

export interface Ward {
  id: number;
  hospital: number;
  hospital_name: string;
  name: string;
  code: string;
  capacity: number;
  occupied_count: number;
  available_count: number;
  beds: Bed[];
  created_at: string;
}

export interface Bed {
  id: number;
  label: string;
  status: "available" | "occupied" | "cleaning" | "maintenance";
  status_display: string;
  patient_nhid: string | null;
  created_at: string;
}

export interface VitalSign {
  id: number;
  encounter?: number;
  recorded_by?: number;
  recorded_by_name?: string;
  recorded_at: string;
  temperature?: number;
  heart_rate?: number;
  respiratory_rate?: number;
  bp_systolic?: number;
  bp_diastolic?: number;
  spo2?: number;
  pain_score?: number;
  weight_kg?: number;
  height_cm?: number;
  created_at: string;
}

export interface LabOrder {
  id: number;
  encounter?: number;
  patient_nhid: string;
  ordered_by?: number;
  ordered_by_name?: string;
  test_name: string;
  loinc_code?: string;
  priority: "routine" | "urgent" | "stat";
  priority_display: string;
  status: "pending" | "in_progress" | "resulted" | "cancelled";
  status_display: string;
  clinical_notes?: string;
  created_at: string;
}

export interface Appointment {
  id: number;
  patient: number | string;
  patient_nhid: string;
  patient_name: string;
  provider?: number;
  provider_name?: string;
  hospital: number;
  hospital_name: string;
  scheduled_for: string;
  duration_minutes: number;
  appointment_type: "outpatient" | "follow_up" | "procedure" | "lab" | "emergency";
  appointment_type_display: string;
  status: "scheduled" | "checked_in" | "in_progress" | "completed" | "no_show" | "cancelled";
  status_display: string;
  reason?: string;
  notes?: string;
  created_at: string;
}

export interface Referral {
  id: number;
  patient: number;
  patient_nhid: string;
  patient_name: string;
  from_hospital: number;
  from_hospital_name: string;
  to_hospital: number;
  to_hospital_name: string;
  from_provider?: number;
  from_provider_name?: string;
  to_provider?: number;
  reason: string;
  priority: "routine" | "urgent" | "stat";
  priority_display: string;
  status: "draft" | "sent" | "accepted" | "rejected" | "completed" | "cancelled";
  status_display: string;
  status_notes?: string;
  created_at: string;
  updated_at: string;
}

export interface ShiftRecord {
  id: number;
  user: number;
  user_name: string;
  ward?: number;
  ward_name?: string;
  started_at: string;
  ended_at?: string;
  break_minutes: number;
  is_active: boolean;
  created_at: string;
}

export interface Handover {
  id: number;
  shift?: number;
  from_user: number;
  from_user_name: string;
  to_user?: number;
  to_user_name?: string;
  ward?: number;
  ward_name?: string;
  summary: string;
  acknowledged_by?: number | null;
  acknowledged_by_name?: string | null;
  acknowledged_at?: string | null;
  created_at: string;
}

export interface AlertFeedItem {
  id: string;
  kind: "LAB_ABNORMAL" | "ALLERGY" | "ALERT";
  label: string;
  severity: "MILD" | "MODERATE" | "SEVERE" | "LIFE_THREAT";
  patient_nhid: string | null;
  patient_name: string | null;
  detail: string;
  timestamp: string;
  is_active: boolean;
}

export interface AlertsFeed {
  count: number;
  results: AlertFeedItem[];
}

export interface ChainNode {
  id: number;
  valid: boolean;
  prev_hash: string;
  row_hash: string;
  action: string;
  actor: string;
  timestamp: string;
}

export interface ChainValidation {
  chain_valid: boolean;
  total_entries: number;
  nodes: ChainNode[];
}

export interface AIQueryResult {
  answer:       string;
  provider:     "gemini" | "ollama";
  model:        string;
  context_size: number;
  configured?:  boolean;
  error?:       string;
}

export interface PatientDocument {
  id: number;
  original_name: string;
  file_type: string;
  file_size: number;
  file_size_kb: number;
  description: string;
  uploaded_by: number | null;
  uploaded_by_name: string | null;
  download_url: string | null;
  created_at: string;
}

export interface PatientRecordsSummary {
  diagnoses:     Diagnosis[];
  prescriptions: Prescription[];
  lab_results:   LabResult[];
  vitals:        VitalSign[];
}

// ── Paginated response ────────────────────────────────────────────────────────

export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

// ── Access decision ───────────────────────────────────────────────────────────

export interface AccessDecision {
  allowed: boolean;
  basis: "admin" | "same_hospital" | "treatment_relationship" | "break_glass" | "denied" | "error";
  is_cross_hospital: boolean;
}

// ── MFA status ────────────────────────────────────────────────────────────────

export interface MfaStatus {
  mfa_enabled: boolean;
  mfa_verified_this_session: boolean;
  mfa_enforced: boolean;
  role_requires_mfa: boolean;
  trusted_device: boolean;
  trusted_device_hours: number;
}

export interface MedicationAdministration {
  id: number;
  prescription: number;
  prescription_drug_name: string;
  prescription_dosage: string;
  prescription_frequency: string;
  patient_name: string;
  patient_nhid: string;
  bed_label: string;
  administered_by: number | null;
  administered_by_name: string | null;
  scheduled_time: string;
  administered_time: string | null;
  status: "due" | "given" | "held" | "refused" | "missed";
  status_display: string;
  notes: string;
}

