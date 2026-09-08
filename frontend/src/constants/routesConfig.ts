import type { Role } from "@/types";
import React from "react";

// Lazy-loaded page component imports for route-level code splitting
const DashboardPage       = React.lazy(() => import("@/pages/dashboard/DashboardPage").then((m) => ({ default: m.DashboardPage })));
const PatientSearchPage   = React.lazy(() => import("@/pages/patients/PatientSearchPage").then((m) => ({ default: m.PatientSearchPage })));
const PatientDetailPage   = React.lazy(() => import("@/pages/patients/PatientDetailPage").then((m) => ({ default: m.PatientDetailPage })));
const PatientFormPage     = React.lazy(() => import("@/pages/patients/PatientFormPage").then((m) => ({ default: m.PatientFormPage })));
const AlertFormPage       = React.lazy(() => import("@/pages/patients/AlertFormPage").then((m) => ({ default: m.AlertFormPage })));
const EncounterDetailPage = React.lazy(() => import("@/pages/records/EncounterDetailPage").then((m) => ({ default: m.EncounterDetailPage })));
const EncounterFormPage   = React.lazy(() => import("@/pages/records/EncounterFormPage").then((m) => ({ default: m.EncounterFormPage })));
const StaffListPage       = React.lazy(() => import("@/pages/staff/StaffListPage").then((m) => ({ default: m.StaffListPage })));
const HospitalListPage    = React.lazy(() => import("@/pages/hospitals/HospitalListPage").then((m) => ({ default: m.HospitalListPage })));
const AuditLogPage        = React.lazy(() => import("@/pages/audit/AuditLogPage").then((m) => ({ default: m.AuditLogPage })));
const ProfilePage         = React.lazy(() => import("@/pages/profile/ProfilePage").then((m) => ({ default: m.ProfilePage })));

const EmergencyQueuePage  = React.lazy(() => import("@/pages/common/EmergencyQueuePage").then((m) => ({ default: m.EmergencyQueuePage })));
const InteropPage         = React.lazy(() => import("@/pages/common/InteropPage").then((m) => ({ default: m.InteropPage })));
const AppointmentsPage    = React.lazy(() => import("@/pages/appointments/AppointmentsPage").then((m) => ({ default: m.AppointmentsPage })));
const AlertsPage          = React.lazy(() => import("@/pages/alerts/AlertsPage").then((m) => ({ default: m.AlertsPage })));
const WorklistPage        = React.lazy(() => import("@/pages/worklist/WorklistPage").then((m) => ({ default: m.WorklistPage })));
const HandoverPage        = React.lazy(() => import("@/pages/worklist/HandoverPage").then((m) => ({ default: m.HandoverPage })));
const ReferralsPage       = React.lazy(() => import("@/pages/referrals/ReferralsPage").then((m) => ({ default: m.ReferralsPage })));
const LabOrdersPage       = React.lazy(() => import("@/pages/lab/LabOrdersPage").then((m) => ({ default: m.LabOrdersPage })));
const FacilitiesPage      = React.lazy(() => import("@/pages/admin/FacilitiesPage").then((m) => ({ default: m.FacilitiesPage })));
const SuperAdminDashboard = React.lazy(() => import("@/pages/superadmin/SuperAdminDashboard").then((m) => ({ default: m.SuperAdminDashboard })));
const AuditLogsPage       = React.lazy(() => import("@/pages/superadmin/AuditLogsPage").then((m) => ({ default: m.AuditLogsPage })));
const AIIntegrationPage   = React.lazy(() => import("@/pages/superadmin/AIIntegrationPage").then((m) => ({ default: m.AIIntegrationPage })));

const PrescriptionsPage   = React.lazy(() => import("@/pages/prescriptions/PrescriptionsPage").then((m) => ({ default: m.PrescriptionsPage })));
const LabResultsPage      = React.lazy(() => import("@/pages/lab/LabResultsPage").then((m) => ({ default: m.LabResultsPage })));
const VitalsPage          = React.lazy(() => import("@/pages/vitals/VitalsPage").then((m) => ({ default: m.VitalsPage })));

const NetworkMapPage        = React.lazy(() => import("@/pages/superadmin/NetworkMapPage").then((m) => ({ default: m.NetworkMapPage })));
const BreakGlassReviewPage  = React.lazy(() => import("@/pages/superadmin/BreakGlassReviewPage").then((m) => ({ default: m.BreakGlassReviewPage })));
const SystemHealthPage      = React.lazy(() => import("@/pages/superadmin/SystemHealthPage").then((m) => ({ default: m.SystemHealthPage })));
const UserManagementPage    = React.lazy(() => import("@/pages/superadmin/UserManagementPage").then((m) => ({ default: m.UserManagementPage })));

const ReportsPage         = React.lazy(() => import("@/pages/admin/ReportsPage").then((m) => ({ default: m.ReportsPage })));
const AdminUsersPage      = React.lazy(() => import("@/pages/admin/AdminUsersPage").then((m) => ({ default: m.AdminUsersPage })));
const ShiftManagementPage = React.lazy(() => import("@/pages/admin/ShiftManagementPage").then((m) => ({ default: m.ShiftManagementPage })));
const AnalyticsPage       = React.lazy(() => import("@/pages/admin/AnalyticsPage").then((m) => ({ default: m.AnalyticsPage })));
const AttendanceLogPage   = React.lazy(() => import("@/pages/admin/AttendanceLogPage").then((m) => ({ default: m.AttendanceLogPage })));

const MARPage     = React.lazy(() => import("@/pages/nurse/MARPage").then((m) => ({ default: m.MARPage })));
const BedMapPage  = React.lazy(() => import("@/pages/nurse/BedMapPage").then((m) => ({ default: m.BedMapPage })));

const WaitingQueuePage = React.lazy(() => import("@/pages/receptionist/WaitingQueuePage").then((m) => ({ default: m.WaitingQueuePage })));

export interface NavConfig {
  label: string;
  icon: string;
  section: string;
}

export interface RouteDefinition {
  path: string;
  element: React.ComponentType;
  roles: Role[];
  nav?: Partial<Record<Role, NavConfig>>;
  isLandingFor?: Role;
  end?: boolean; // Exact match for NavLink
}

const ALL_ROLES: Role[] = ["super_admin", "hospital_admin", "doctor", "nurse", "lab_technician", "receptionist"];
const CLINICAL_ROLES: Role[] = ["doctor", "nurse", "lab_technician"];
const CLINICAL_AND_ADMIN: Role[] = ["doctor", "nurse", "lab_technician", "hospital_admin", "super_admin"];
const ADMIN_ROLES: Role[] = ["hospital_admin", "super_admin"];

export const routesConfig: RouteDefinition[] = [
  // ── Shared Dashboard & Profile ──────────────────────────────────────────────
  {
    path: "/",
    element: DashboardPage,
    roles: ["doctor", "nurse", "hospital_admin"], // receptionist & lab tech redirect to workspace
    isLandingFor: "doctor", // doctor & nurse landing defaults to shared dashboard
    end: true,
  },
  {
    path: "profile",
    element: ProfilePage,
    roles: ALL_ROLES,
  },
  {
    path: "hospitals",
    element: HospitalListPage,
    roles: ALL_ROLES,
  },

  // ── Patients (Clinical / Front Desk) ─────────────────────────────────────────
  {
    path: "patients",
    element: PatientSearchPage,
    roles: ["doctor", "nurse", "receptionist", "hospital_admin", "super_admin"],
    nav: {
      doctor: { label: "Search patients", icon: "IconSearch", section: "PATIENTS" },
      nurse: { label: "My ward", icon: "IconSearch", section: "WARD" },
      receptionist: { label: "Patient directory", icon: "IconSearch", section: "FRONT DESK" },
    },
  },
  {
    path: "patients/new",
    element: PatientFormPage,
    roles: ["doctor", "nurse", "receptionist", "hospital_admin", "super_admin"],
  },
  {
    path: "patients/:nhid",
    element: PatientDetailPage,
    roles: ["doctor", "nurse", "receptionist", "hospital_admin", "super_admin"],
  },
  {
    path: "patients/:nhid/edit",
    element: PatientFormPage,
    roles: ["doctor", "nurse", "receptionist", "hospital_admin", "super_admin"],
  },
  {
    path: "patients/:nhid/alerts/new",
    element: AlertFormPage,
    roles: ["doctor", "nurse"],
  },
  {
    path: "patients/:nhid/encounters/new",
    element: EncounterFormPage,
    roles: ["doctor", "nurse"],
  },

  // ── Clinical records ────────────────────────────────────────────────────────
  {
    path: "encounters/:id",
    element: EncounterDetailPage,
    roles: ["doctor", "nurse"],
  },

  // ── Shared clinical pages ────────────────────────────────────────────────────
  {
    path: "appointments",
    element: AppointmentsPage,
    roles: ["doctor", "nurse", "receptionist", "hospital_admin", "super_admin"],
    nav: {
      doctor: { label: "Appointments", icon: "IconCalendar", section: "PATIENTS" },
      hospital_admin: { label: "Appointments", icon: "IconCalendar", section: "MONITORING" },
      receptionist: { label: "Appointments", icon: "IconCalendar", section: "FRONT DESK" },
    },
  },
  {
    path: "alerts",
    element: AlertsPage,
    roles: CLINICAL_AND_ADMIN,
    nav: {
      doctor: { label: "Alerts", icon: "IconAlertTriangle", section: "ALERTS" },
      nurse: { label: "Alerts", icon: "IconAlertTriangle", section: "ALERTS" },
      hospital_admin: { label: "Alerts", icon: "IconAlertTriangle", section: "MONITORING" },
    },
  },
  {
    path: "emergency",
    element: EmergencyQueuePage,
    roles: ALL_ROLES,
    nav: {
      doctor: { label: "Emergency queue", icon: "IconUrgent", section: "CLINICAL" },
      nurse: { label: "Emergency", icon: "IconUrgent", section: "WARD" },
      receptionist: { label: "Emergency queue", icon: "IconUrgent", section: "FRONT DESK" },
    },
  },

  // ── Clinical: Prescription Writer (Doctor only) ──────────────────────────────
  {
    path: "prescriptions",
    element: PrescriptionsPage,
    roles: ["doctor"],
    nav: {
      doctor: { label: "Prescriptions", icon: "IconPill", section: "PATIENTS" },
    },
  },

  // ── Clinical: Vitals (Doctor + Nurse) ────────────────────────────────────────
  {
    path: "vitals",
    element: VitalsPage,
    roles: ["doctor", "nurse"],
    nav: {
      doctor: { label: "Vitals", icon: "IconHeartbeat", section: "PATIENTS" },
      nurse: { label: "Vitals", icon: "IconHeartbeat", section: "CLINICAL" },
    },
  },

  // ── Doctor / Nurse Shared ───────────────────────────────────────────────────
  {
    path: "worklist",
    element: WorklistPage,
    roles: ["doctor", "nurse"],
    nav: {
      doctor: { label: "My worklist", icon: "IconClipboardList", section: "CLINICAL" },
    },
  },
  {
    path: "worklist/handover",
    element: HandoverPage,
    roles: ["nurse"],
    nav: {
      nurse: { label: "Handover", icon: "IconClipboardList", section: "SHIFTS" },
    },
  },
  {
    path: "referrals",
    element: ReferralsPage,
    roles: ["doctor", "hospital_admin", "super_admin"],
    nav: {
      doctor: { label: "Referrals", icon: "IconArrowLeftRight", section: "NETWORK" },
      hospital_admin: { label: "Referrals", icon: "IconArrowLeftRight", section: "MONITORING" },
      super_admin: { label: "Referral network", icon: "IconArrowLeftRight", section: "CONFIGURATION" },
    },
  },
  {
    path: "interop",
    element: InteropPage,
    roles: ["doctor"],
    nav: {
      doctor: { label: "Inter-hospital", icon: "IconBuilding", section: "NETWORK" },
    },
  },
  {
    path: "admissions",
    element: BedMapPage,
    roles: ["nurse", "hospital_admin", "super_admin"],
    nav: {
      hospital_admin: { label: "Admissions", icon: "IconBuilding", section: "MONITORING" },
    },
  },

  // ── Nurse-specific ──────────────────────────────────────────────────────────
  {
    path: "nurse/mar",
    element: MARPage,
    roles: ["nurse"],
    nav: {
      nurse: { label: "MAR", icon: "IconPill", section: "CLINICAL" },
    },
  },
  {
    path: "nurse/beds",
    element: BedMapPage,
    roles: ["nurse"],
    nav: {
      nurse: { label: "Bed map", icon: "IconBed", section: "WARD" },
    },
  },

  // ── Receptionist-specific ────────────────────────────────────────────────────
  {
    path: "receptionist/queue",
    element: WaitingQueuePage,
    roles: ["receptionist"],
    isLandingFor: "receptionist",
    nav: {
      receptionist: { label: "Waiting queue", icon: "IconClock", section: "FRONT DESK" },
    },
  },

  // ── Laboratory ───────────────────────────────────────────────────────────────
  {
    path: "lab/orders",
    element: LabOrdersPage,
    roles: CLINICAL_ROLES,
    isLandingFor: "lab_technician",
    nav: {
      lab_technician: { label: "Order worklist", icon: "IconFlask", section: "LABORATORY" },
    },
  },
  {
    path: "lab/results",
    element: LabResultsPage,
    roles: CLINICAL_ROLES,
    nav: {
      lab_technician: { label: "Enter results", icon: "IconClipboardList", section: "LABORATORY" },
    },
  },

  // ── Staff management ─────────────────────────────────────────────────────────
  {
    path: "staff",
    element: StaffListPage,
    roles: ADMIN_ROLES,
  },

  // ── Hospital Admin section ──────────────────────────────────────────────────
  {
    path: "admin/users",
    element: AdminUsersPage,
    roles: ADMIN_ROLES,
    isLandingFor: "hospital_admin",
    nav: {
      hospital_admin: { label: "Users", icon: "IconUsers", section: "STAFF" },
    },
  },
  {
    path: "admin/shift-management",
    element: ShiftManagementPage,
    roles: ADMIN_ROLES,
    nav: {
      hospital_admin: { label: "Shift management", icon: "IconClock", section: "STAFF" },
    },
  },
  {
    path: "admin/facilities",
    element: FacilitiesPage,
    roles: ADMIN_ROLES,
    nav: {
      hospital_admin: { label: "Wards & beds", icon: "IconBuilding", section: "FACILITY" },
    },
  },
  {
    path: "admin/audit-logs",
    element: AuditLogPage,
    roles: ADMIN_ROLES,
    nav: {
      hospital_admin: { label: "Audit logs", icon: "IconShieldLock", section: "FACILITY" },
    },
  },
  {
    path: "admin/reports",
    element: ReportsPage,
    roles: ADMIN_ROLES,
    nav: {
      hospital_admin: { label: "Reports", icon: "IconChartBar", section: "OVERVIEW" },
    },
  },
  {
    path: "admin/analytics",
    element: AnalyticsPage,
    roles: ADMIN_ROLES,
    nav: {
      hospital_admin: { label: "Analytics", icon: "IconActivity", section: "OVERVIEW" },
    },
  },
  {
    path: "admin/attendance",
    element: AttendanceLogPage,
    roles: ADMIN_ROLES,
    nav: {
      hospital_admin: { label: "Attendance log", icon: "IconClock", section: "STAFF" },
    },
  },

  // ── Super Admin section ──────────────────────────────────────────────────────
  {
    path: "superadmin",
    element: SuperAdminDashboard,
    roles: ["super_admin"],
    isLandingFor: "super_admin",
    nav: {
      super_admin: { label: "Dashboard", icon: "IconLayoutDashboard", section: "OVERVIEW" },
    },
    end: true,
  },
  {
    path: "superadmin/system-health",
    element: SystemHealthPage,
    roles: ["super_admin"],
    nav: {
      super_admin: { label: "System health", icon: "IconActivity", section: "OVERVIEW" },
    },
  },
  {
    path: "superadmin/hospitals",
    element: HospitalListPage,
    roles: ["super_admin"],
    nav: {
      super_admin: { label: "All hospitals", icon: "IconBuilding", section: "HOSPITALS" },
    },
  },
  {
    path: "superadmin/network",
    element: NetworkMapPage,
    roles: ["super_admin"],
    nav: {
      super_admin: { label: "Network map", icon: "IconNetwork", section: "HOSPITALS" },
    },
  },
  {
    path: "superadmin/audit-logs",
    element: AuditLogsPage,
    roles: ["super_admin"],
    nav: {
      super_admin: { label: "Audit logs", icon: "IconShieldLock", section: "SECURITY" },
    },
  },
  {
    path: "superadmin/break-glass-review",
    element: BreakGlassReviewPage,
    roles: ["super_admin"],
    nav: {
      super_admin: { label: "Break-glass review", icon: "IconUserPlus", section: "SECURITY" },
    },
  },
  {
    path: "superadmin/user-management",
    element: UserManagementPage,
    roles: ["super_admin"],
    nav: {
      super_admin: { label: "User management", icon: "IconUsers", section: "SECURITY" },
    },
  },
  {
    path: "superadmin/ai-integration",
    element: AIIntegrationPage,
    roles: ["super_admin"],
    nav: {
      super_admin: { label: "AI integration", icon: "IconBrain", section: "CONFIGURATION" },
    },
  },
];
