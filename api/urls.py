"""URL routing for the mEd REST API (mounted at /api/)."""

from django.urls import path

from ai.views import PatientAIQueryView
from api.views.alerts_feed import AlertsFeedView
from api.views.appointments import (
    AppointmentDetailView,
    AppointmentListCreateView,
    AppointmentStatusView,
)
from api.views.audit import (
    AuditActionChoicesView,
    AuditChainValidateView,
    AuditLogListView,
    AuditLogReviewView,
)
from api.views.auth import (
    CsrfView,
    LoginView,
    LogoutView,
    MeView,
    PasswordChangeView,
)
from api.views.dashboard import DashboardView
from api.views.documents import (
    PatientDocumentDeleteView,
    PatientDocumentDownloadView,
    PatientDocumentListUploadView,
)
from api.views.hospitals import HospitalDetailView, HospitalListCreateView
from api.views.lab_orders import (
    LabOrderDetailView,
    LabOrderStatusView,
    LabOrderWorklistView,
    PatientLabOrderListCreateView,
)
from api.views.mfa import (
    MfaDisableView,
    MfaRegenerateCodesView,
    MfaSetupView,
    MfaStatusView,
    MfaVerifyView,
    SendEmailOtpView,
    SignoutAllView,
)
from api.views.patients import (
    AlertDeactivateView,
    BreakGlassView,
    PatientAccessView,
    PatientAlertCreateView,
    PatientCreateView,
    PatientDetailView,
    PatientEncounterListCreateView,
    PatientSearchView,
)
from api.views.records import (
    DiagnosisCreateView,
    EncounterDetailView,
    LabResultCreateView,
    MedicationAdministrationListView,
    MedicationAdministrationUpdateStatusView,
    PatientRecordsSummaryView,
    PrescriptionCreateView,
)
from api.views.consent_views import (
    PatientConsentDetailView,
    PatientConsentListCreateView,
)
from api.views.referrals_views import ReferralListCreateView, ReferralStatusView
from api.views.shifts_views import (
    HandoverAcknowledgeView,
    HandoverListCreateView,
    ShiftEndView,
    ShiftListView,
    ShiftStartView,
)
from api.views.staff import (
    StaffDetailView,
    StaffListCreateView,
    StaffResetPasswordView,
    StaffSetActiveView,
)

# ── Phase B — new clinical domain views ──────────────────────────────────────
from api.views.vitals import PatientVitalListCreateView
from api.views.wards import BedStatusView, WardDetailView, WardListCreateView

urlpatterns = [
    # ── Auth ──────────────────────────────────────────────────────────────────
    path("csrf/", CsrfView.as_view(), name="api-csrf"),
    path("me/", MeView.as_view(), name="api-me"),
    path("auth/login/", LoginView.as_view(), name="api-login"),
    path("auth/logout/", LogoutView.as_view(), name="api-logout"),
    path("auth/password/change/", PasswordChangeView.as_view(), name="api-password-change"),
    # ── MFA ───────────────────────────────────────────────────────────────────
    path("mfa/status/", MfaStatusView.as_view(), name="api-mfa-status"),
    path("mfa/setup/", MfaSetupView.as_view(), name="api-mfa-setup"),
    path("mfa/verify/", MfaVerifyView.as_view(), name="api-mfa-verify"),
    path("mfa/send-email-otp/", SendEmailOtpView.as_view(), name="api-mfa-send-email-otp"),
    path("mfa/disable/", MfaDisableView.as_view(), name="api-mfa-disable"),
    path("mfa/regenerate-codes/", MfaRegenerateCodesView.as_view(), name="api-mfa-regen"),
    path("security/signout-all/", SignoutAllView.as_view(), name="api-signout-all"),
    # ── Dashboard ─────────────────────────────────────────────────────────────
    path("dashboard/", DashboardView.as_view(), name="api-dashboard"),
    # ── Patients ──────────────────────────────────────────────────────────────
    path("patients/", PatientSearchView.as_view(), name="api-patient-search"),
    path("patients/new/", PatientCreateView.as_view(), name="api-patient-create"),
    path("patients/<str:universal_id>/", PatientDetailView.as_view(), name="api-patient-detail"),
    path(
        "patients/<str:universal_id>/access/",
        PatientAccessView.as_view(),
        name="api-patient-access",
    ),
    path(
        "patients/<str:universal_id>/break-glass/", BreakGlassView.as_view(), name="api-break-glass"
    ),
    path(
        "patients/<str:universal_id>/encounters/",
        PatientEncounterListCreateView.as_view(),
        name="api-patient-encounters",
    ),
    path(
        "patients/<str:universal_id>/alerts/",
        PatientAlertCreateView.as_view(),
        name="api-patient-alerts",
    ),
    path(
        "patients/<str:universal_id>/alerts/<int:alert_pk>/deactivate/",
        AlertDeactivateView.as_view(),
        name="api-alert-deactivate",
    ),
    # Phase B — vitals and lab orders per patient
    path(
        "patients/<str:universal_id>/vitals/",
        PatientVitalListCreateView.as_view(),
        name="api-patient-vitals",
    ),
    path(
        "patients/<str:universal_id>/lab-orders/",
        PatientLabOrderListCreateView.as_view(),
        name="api-patient-lab-orders",
    ),
    # Phase D — patient chart tab system
    path(
        "patients/<str:universal_id>/records-summary/",
        PatientRecordsSummaryView.as_view(),
        name="api-patient-records-summary",
    ),
    # Phase E — AI query
    path(
        "patients/<str:universal_id>/ai-query/",
        PatientAIQueryView.as_view(),
        name="api-patient-ai-query",
    ),
    # Documents
    path(
        "patients/<str:nhid>/documents/",
        PatientDocumentListUploadView.as_view(),
        name="api-patient-documents",
    ),
    path(
        "patients/<str:nhid>/documents/<int:pk>/download/",
        PatientDocumentDownloadView.as_view(),
        name="api-patient-document-download",
    ),
    path(
        "patients/<str:nhid>/documents/<int:pk>/",
        PatientDocumentDeleteView.as_view(),
        name="api-patient-document-delete",
    ),
    # ── Encounters ────────────────────────────────────────────────────────────
    path("encounters/<int:pk>/", EncounterDetailView.as_view(), name="api-encounter-detail"),
    path(
        "encounters/<int:pk>/diagnoses/", DiagnosisCreateView.as_view(), name="api-diagnosis-create"
    ),
    path(
        "encounters/<int:pk>/prescriptions/",
        PrescriptionCreateView.as_view(),
        name="api-prescription-create",
    ),
    path("encounters/<int:pk>/lab-results/", LabResultCreateView.as_view(), name="api-lab-create"),
    path("med-admins/", MedicationAdministrationListView.as_view(), name="api-med-admins"),
    path(
        "med-admins/<int:pk>/status/",
        MedicationAdministrationUpdateStatusView.as_view(),
        name="api-med-admins-status",
    ),
    # ── Staff ─────────────────────────────────────────────────────────────────
    path("staff/", StaffListCreateView.as_view(), name="api-staff-list"),
    path("staff/<int:pk>/", StaffDetailView.as_view(), name="api-staff-detail"),
    path("staff/<int:pk>/set-active/", StaffSetActiveView.as_view(), name="api-staff-set-active"),
    path(
        "staff/<int:pk>/reset-password/",
        StaffResetPasswordView.as_view(),
        name="api-staff-reset-password",
    ),
    # ── Hospitals ─────────────────────────────────────────────────────────────
    path("hospitals/", HospitalListCreateView.as_view(), name="api-hospital-list"),
    path("hospitals/<int:pk>/", HospitalDetailView.as_view(), name="api-hospital-detail"),
    # ── Audit ─────────────────────────────────────────────────────────────────
    path("audit/", AuditLogListView.as_view(), name="api-audit-log"),
    path("audit/actions/", AuditActionChoicesView.as_view(), name="api-audit-actions"),
    path("audit/validate-chain/", AuditChainValidateView.as_view(), name="api-audit-chain"),
    path("audit/<int:pk>/review/", AuditLogReviewView.as_view(), name="api-audit-review"),
    # ── Alerts feed ───────────────────────────────────────────────────────────
    path("alerts/", AlertsFeedView.as_view(), name="api-alerts-feed"),
    # ── Appointments ──────────────────────────────────────────────────────────
    path("appointments/", AppointmentListCreateView.as_view(), name="api-appointments"),
    path("appointments/<int:pk>/", AppointmentDetailView.as_view(), name="api-appointment-detail"),
    path(
        "appointments/<int:pk>/status/",
        AppointmentStatusView.as_view(),
        name="api-appointment-status",
    ),
    # ── Referrals ─────────────────────────────────────────────────────────────
    path("referrals/", ReferralListCreateView.as_view(), name="api-referrals"),
    path("referrals/<int:pk>/status/", ReferralStatusView.as_view(), name="api-referral-status"),
    # ── Consents ──────────────────────────────────────────────────────────────
    path("consents/", PatientConsentListCreateView.as_view(), name="api-consents"),
    path("consents/<int:pk>/", PatientConsentDetailView.as_view(), name="api-consent-detail"),
    # ── Wards & Beds ──────────────────────────────────────────────────────────
    path("wards/", WardListCreateView.as_view(), name="api-wards"),
    path("wards/<int:pk>/", WardDetailView.as_view(), name="api-ward-detail"),
    path("beds/<int:pk>/status/", BedStatusView.as_view(), name="api-bed-status"),
    # ── Lab orders (worklist) ─────────────────────────────────────────────────
    path("lab-orders/worklist/", LabOrderWorklistView.as_view(), name="api-lab-worklist"),
    path("lab-orders/<int:pk>/", LabOrderDetailView.as_view(), name="api-lab-order-detail"),
    path("lab-orders/<int:pk>/status/", LabOrderStatusView.as_view(), name="api-lab-order-status"),
    # ── Shifts & Handovers ────────────────────────────────────────────────────
    path("shifts/", ShiftListView.as_view(), name="api-shifts"),
    path("shifts/start/", ShiftStartView.as_view(), name="api-shift-start"),
    path("shifts/<int:pk>/end/", ShiftEndView.as_view(), name="api-shift-end"),
    path("handovers/", HandoverListCreateView.as_view(), name="api-handovers"),
    path(
        "handovers/<int:pk>/acknowledge/",
        HandoverAcknowledgeView.as_view(),
        name="api-handover-acknowledge",
    ),
]
