"""
Alerts feed — aggregates critical alerts for the current user's scope.

Sources:
  1. Active PatientAlerts (allergies / clinical alerts)
  2. Abnormal LabResults from the last 7 days
  3. (Future: overdue vitals)

Returns a unified list sorted by severity, newest first.
"""

from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from api.permissions import CanViewAlerts
from patients.models import Patient, PatientAlert
from records.models import LabResult


class AlertsFeedView(APIView):
    """GET /api/alerts/ — scoped alerts feed for the current user."""

    permission_classes = [IsAuthenticated, CanViewAlerts]

    def get(self, request):
        user = request.user
        alerts = []
        cutoff = timezone.now() - timezone.timedelta(days=7)

        if user.role in ("super_admin",):
            # Superadmin: recent abnormal labs across all hospitals
            lab_qs = (
                LabResult.objects.filter(is_abnormal=True, created_at__gte=cutoff)
                .select_related("encounter__patient")
                .order_by("-created_at")[:50]
            )
        elif user.role in ("hospital_admin", "doctor", "nurse"):
            lab_qs = (
                LabResult.objects.filter(
                    is_abnormal=True,
                    created_at__gte=cutoff,
                    encounter__created_at_hospital=user.hospital,
                )
                .select_related("encounter__patient")
                .order_by("-created_at")[:50]
            )
        else:
            lab_qs = LabResult.objects.none()

        for lab in lab_qs:
            patient = lab.encounter.patient if lab.encounter else None
            result_str = str(lab.result_value or "").upper()
            if "CRITICAL" in result_str or "PANIC" in result_str:
                severity = "LIFE_THREAT"
            elif lab.is_abnormal:
                severity = "SEVERE"
            else:
                severity = "MILD"
            alerts.append(
                {
                    "id": f"lab-{lab.pk}",
                    "kind": "LAB_ABNORMAL",
                    "label": lab.test_name,
                    "severity": severity,
                    "patient_nhid": patient.universal_id if patient else None,
                    "patient_name": f"{patient.first_name} {patient.last_name}"
                    if patient
                    else None,
                    "detail": str(lab.result_value)[:200],
                    "timestamp": lab.created_at.isoformat(),
                    "is_active": True,
                }
            )

        # Active PatientAlerts in scope
        if user.role in ("super_admin",):
            alert_qs = PatientAlert.objects.filter(is_active=True)
        elif user.role in ("hospital_admin", "doctor", "nurse"):
            patient_ids = Patient.objects.filter(registered_at_hospital=user.hospital).values_list(
                "pk", flat=True
            )
            alert_qs = PatientAlert.objects.filter(is_active=True, patient_id__in=patient_ids)
        else:
            alert_qs = PatientAlert.objects.none()

        alert_qs = alert_qs.select_related("patient").order_by("-severity", "-created_at")[:50]
        for pa in alert_qs:
            alerts.append(
                {
                    "id": f"patient-alert-{pa.pk}",
                    "kind": pa.kind,
                    "label": str(pa.label),
                    "severity": pa.severity,
                    "patient_nhid": pa.patient.universal_id,
                    "patient_name": f"{pa.patient.first_name} {pa.patient.last_name}",
                    "detail": str(pa.reaction)[:200] if pa.reaction else "",
                    "timestamp": pa.created_at.isoformat(),
                    "is_active": pa.is_active,
                }
            )

        # Sort: LIFE_THREAT first, then newest first within each severity tier.
        # Two-pass stable sort: secondary key (timestamp descending) then primary key (severity ascending).
        severity_order = {"LIFE_THREAT": 0, "SEVERE": 1, "MODERATE": 2, "MILD": 3}
        alerts.sort(key=lambda a: a["timestamp"], reverse=True)
        alerts.sort(key=lambda a: severity_order.get(a["severity"], 99))

        return Response(
            {
                "count": len(alerts),
                "results": alerts,
            }
        )
