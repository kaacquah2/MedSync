"""
Patient API views — search, register, detail, access gate, break-glass, alerts.

Each view calls the same authorisation seams as the Django template views:
  - can_access_patient()  for inter-hospital access decisions
  - log_action()          for every significant action
  - ensure_treatment_relationship()  auto-created when an encounter is opened
"""

import logging

from django.core.cache import cache
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from access.models import BREAK_GLASS_DURATION_HOURS, BreakGlassAccess
from access.permissions import can_access_patient
from api.permissions import BreakGlassThrottle, CanRegisterPatient, CanCreateEncounter, IsAdminOrClinical, IsDoctorOrNurse
from api.serializers import (
    EncounterListSerializer,
    EncounterSerializer,
    PatientAlertSerializer,
    PatientListSerializer,
    PatientSerializer,
)
from audit.utils import log_action
from core.blind_index import make_blind_index
from patients.models import Patient, PatientAlert
from records.models import Encounter

logger = logging.getLogger(__name__)

_SEARCH_RATE_LIMIT = 30
_SEARCH_RATE_WINDOW = 60


def _check_rate_limit(user) -> bool:
    key = f"api_patient_search_rate:{user.pk}"
    # cache.add is atomic and only sets when the key is absent (fixed window start).
    # cache.incr is atomic on Redis/Memcached, eliminating the TOCTOU race.
    cache.add(key, 0, timeout=_SEARCH_RATE_WINDOW)
    count = cache.incr(key)
    return count > _SEARCH_RATE_LIMIT


class PatientSearchView(APIView):
    """
    GET /api/patients/?q=<query>&page=<n>

    Search strategy mirrors patients/views.py:
      1. Exact NHID match (indexed)
      2. Blind-index on full name and national ID (indexed)
      3. Partial name scan (O(n) — documented limitation)
    """

    permission_classes = [IsAuthenticated, CanRegisterPatient]

    def get(self, request):
        q = request.GET.get("q", "").strip()

        if q and _check_rate_limit(request.user):
            return Response(
                {"error": "Search rate limit reached. Please wait before searching again."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        patients = []

        if q:
            q_upper = q.upper()

            if q_upper.startswith("NHID-"):
                patients = list(
                    Patient.objects.filter(universal_id__iexact=q_upper).select_related(
                        "registered_at_hospital"
                    )
                )
            else:
                from django.db.models import Q

                hash_value = make_blind_index(q)

                exact_qs = Patient.objects.filter(
                    Q(name_hash=hash_value) | Q(national_id_hash=hash_value)
                ).select_related("registered_at_hospital")

                seen = set()
                for p in exact_qs:
                    if p.pk not in seen:
                        patients.append(p)
                        seen.add(p.pk)

            if not patients or len(q) < 5:
                # O(n) scan — capped at 200 to prevent unbounded memory use on large
                # deployments.  Results are paginated further below.
                if not request.user.is_admin_level:
                    scan_qs = Patient.objects.filter(
                        registered_at_hospital=request.user.hospital
                    ).select_related("registered_at_hospital")[:200]
                else:
                    scan_qs = Patient.objects.select_related("registered_at_hospital")[:200]
                q_lower = q.lower()
                for p in scan_qs:
                    if p.pk in seen:
                        continue
                    try:
                        full = f"{p.first_name} {p.last_name}".lower()
                        if q_lower in full:
                            patients.append(p)
                            seen.add(p.pk)
                    except Exception:
                        pass

            if q:
                import hashlib
                hashed_query = hashlib.sha256(q.encode("utf-8")).hexdigest()
                log_action(
                    request,
                    action="SEARCH_PATIENT",
                    extra={"query_hash": hashed_query, "results": len(patients)},
                )

        # Manual pagination
        from rest_framework.pagination import PageNumberPagination

        paginator = PageNumberPagination()
        paginator.page_size = 20
        page = paginator.paginate_queryset(patients, request)
        serializer = PatientListSerializer(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)


class PatientCreateView(APIView):
    """POST /api/patients/ — register a new patient."""

    permission_classes = [IsAuthenticated, CanRegisterPatient]

    def post(self, request):
        from patients.empi import match_patient

        serializer = PatientSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # EMPI duplicate check
        national_id = str(data.get("national_id", ""))
        first_name = str(data.get("first_name", ""))
        last_name = str(data.get("last_name", ""))
        dob = str(data.get("date_of_birth", ""))

        match = match_patient(
            national_id=national_id,
            name=f"{first_name} {last_name}",
            dob=dob,
        )

        if match.confidence in ("exact", "conflict"):
            return Response(
                {
                    "error": f"Duplicate detected: {match.message}",
                    "empi_confidence": match.confidence,
                    "candidates": [c.universal_id for c in match.candidates],
                },
                status=status.HTTP_409_CONFLICT,
            )

        if match.confidence == "probable" and not request.data.get("confirm_new"):
            return Response(
                {
                    "warning": f"Possible duplicate: {match.message}",
                    "empi_confidence": "probable",
                    "candidates": [c.universal_id for c in match.candidates],
                    "confirm_new_required": True,
                },
                status=status.HTTP_202_ACCEPTED,
            )

        patient = Patient(
            registered_at_hospital=request.user.hospital,
            registered_by=request.user,
            **{
                k: v
                for k, v in data.items()
                if k not in ("registered_at_hospital", "registered_by")
            },
        )
        patient.save()

        log_action(request, action="CREATE_PATIENT", target=patient, patient=patient)
        return Response(
            PatientSerializer(patient, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class PatientDetailView(APIView):
    """
    GET   /api/patients/<nhid>/  — patient detail (access-gated)
    PATCH /api/patients/<nhid>/  — update demographics
    """

    permission_classes = [IsAuthenticated, CanRegisterPatient]

    def _get_patient_or_403(self, request, universal_id):
        from django.db.models import Count, Q
        patient = get_object_or_404(
            Patient.objects.annotate(
                active_alerts_count=Count("alerts", filter=Q(alerts__is_active=True))
            ).select_related("registered_at_hospital", "registered_by"),
            universal_id=universal_id,
        )
        decision = can_access_patient(request.user, patient)
        return patient, decision

    def get(self, request, universal_id):
        patient, decision = self._get_patient_or_403(request, universal_id)

        if not decision:
            log_action(
                request,
                action="ACCESS_DENIED",
                target=patient,
                patient=patient,
                is_cross_hospital=True,
            )
            return Response(
                {
                    "error": "Access denied.",
                    "universal_id": universal_id,
                    "can_break_glass": True,
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        is_cross = (
            request.user.hospital is not None
            and patient.registered_at_hospital is not None
            and request.user.hospital_id != patient.registered_at_hospital_id
        )
        log_action(
            request,
            action="VIEW_PATIENT",
            target=patient,
            patient=patient,
            is_cross_hospital=is_cross,
        )

        serializer = PatientSerializer(patient, context={"request": request})
        data = serializer.data
        data["access_basis"] = decision.basis
        data["is_cross_hospital"] = is_cross

        # Include alerts
        alerts = patient.alerts.select_related("recorded_by", "recorded_at_hospital")
        data["alerts"] = PatientAlertSerializer(
            alerts, many=True, context={"request": request}
        ).data

        return Response(data)

    def patch(self, request, universal_id):
        patient, decision = self._get_patient_or_403(request, universal_id)

        if not decision:
            return Response({"error": "Access denied."}, status=status.HTTP_403_FORBIDDEN)

        # Check role — same as the template view
        if not _has_edit_role(request.user):
            return Response({"error": "Insufficient role."}, status=status.HTTP_403_FORBIDDEN)

        serializer = PatientSerializer(
            patient, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        log_action(request, action="UPDATE_PATIENT", target=patient, patient=patient)
        return Response(serializer.data)


def _has_edit_role(user):
    return user.role in ("doctor", "nurse", "receptionist", "hospital_admin", "super_admin")


class PatientAccessView(APIView):
    """
    GET /api/patients/<nhid>/access/
    Returns { allowed, basis } — the SPA uses this to decide which
    banner/widget to show on the patient detail page.
    """

    permission_classes = [IsAuthenticated, CanRegisterPatient]

    def get(self, request, universal_id):
        patient = get_object_or_404(Patient, universal_id=universal_id)
        decision = can_access_patient(request.user, patient)

        is_cross = (
            request.user.hospital is not None
            and patient.registered_at_hospital is not None
            and request.user.hospital_id != patient.registered_at_hospital_id
        )

        return Response(
            {
                "allowed": decision.allowed,
                "basis": decision.basis,
                "is_cross_hospital": is_cross,
            }
        )


class BreakGlassView(APIView):
    """
    POST /api/patients/<nhid>/break-glass/
    Body: { "reason": "...", "code": "..." (optional, needed when MFA enforced) }

    Creates a BreakGlassAccess grant (1 hour) and audits it.
    Rate-limited to 5/hour per user via BreakGlassThrottle.
    """

    permission_classes = [IsAuthenticated, IsDoctorOrNurse]
    throttle_classes = [BreakGlassThrottle]

    def post(self, request, universal_id):
        from django.conf import settings
        from django.db import transaction
        from django_otp.plugins.otp_totp.models import TOTPDevice

        patient = get_object_or_404(Patient, universal_id=universal_id)
        reason = request.data.get("reason", "").strip()

        if len(reason) < 20:
            return Response(
                {"error": "A clinical justification of at least 20 characters is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        mfa_reverified = False

        # Re-verify TOTP when MFA is enforced and user has a confirmed device
        if getattr(settings, "MFA_ENFORCED", False):
            device = TOTPDevice.objects.filter(user=request.user, confirmed=True).first()
            if device:
                code = request.data.get("code", "").strip()
                if not code or not device.verify_token(code):
                    return Response(
                        {"error": "A valid TOTP code is required to break glass."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                mfa_reverified = True

        expires_at = timezone.now() + timezone.timedelta(hours=BREAK_GLASS_DURATION_HOURS)

        # Use select_for_update inside a transaction to prevent duplicate concurrent grants
        with transaction.atomic():
            # Find an existing active (non-expired) grant to avoid duplicate creation
            existing = (
                BreakGlassAccess.objects.select_for_update()
                .filter(actor=request.user, patient=patient, expires_at__gt=timezone.now())
                .first()
            )
            if existing:
                bg = existing
            else:
                bg = BreakGlassAccess.objects.create(
                    actor=request.user,
                    patient=patient,
                    reason=reason,
                    expires_at=expires_at,
                    mfa_reverified=mfa_reverified,
                )

        log_action(
            request,
            action="BREAK_GLASS",
            target=patient,
            patient=patient,
            is_cross_hospital=True,
            extra={"reason": reason[:200], "expires_at": bg.expires_at.isoformat()},
        )

        return Response(
            {
                "detail": "Break-glass access granted for 1 hour.",
                "expires_at": bg.expires_at.isoformat(),
                "mfa_reverified": mfa_reverified,
            },
            status=status.HTTP_201_CREATED,
        )


# ── Encounters ────────────────────────────────────────────────────────────────


class PatientEncounterListCreateView(APIView):
    """
    GET  /api/patients/<nhid>/encounters/
    POST /api/patients/<nhid>/encounters/
    """

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), CanCreateEncounter()]
        return [IsAuthenticated(), IsAdminOrClinical()]

    def get(self, request, universal_id):
        patient = get_object_or_404(Patient, universal_id=universal_id)
        if not can_access_patient(request.user, patient):
            log_action(
                request,
                action="ACCESS_DENIED",
                target=patient,
                patient=patient,
                is_cross_hospital=True,
            )
            return Response({"error": "Access denied."}, status=status.HTTP_403_FORBIDDEN)

        is_cross = (
            request.user.hospital is not None
            and patient.registered_at_hospital is not None
            and request.user.hospital_id != patient.registered_at_hospital_id
        )
        log_action(
            request,
            action="VIEW_PATIENT",
            target=patient,
            patient=patient,
            is_cross_hospital=is_cross,
        )

        from django.db.models import Exists, OuterRef
        from rest_framework.pagination import PageNumberPagination

        from records.models import LabResult
        abnormal_labs = LabResult.objects.filter(encounter=OuterRef("pk"), is_abnormal=True)
        encounters = patient.encounters.select_related(
            "created_by", "created_at_hospital"
        ).annotate(
            has_abnormal_labs=Exists(abnormal_labs)
        ).order_by("-created_at")

        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(encounters, request)
        serializer = EncounterListSerializer(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)

    def post(self, request, universal_id):
        from access.permissions import ensure_treatment_relationship

        # Role gate delegated to CanCreateEncounter permission class — no inline check needed.
        patient = get_object_or_404(Patient, universal_id=universal_id)
        if not can_access_patient(request.user, patient):
            log_action(
                request,
                action="ACCESS_DENIED",
                target=patient,
                patient=patient,
                is_cross_hospital=True,
            )
            return Response({"error": "Access denied."}, status=status.HTTP_403_FORBIDDEN)

        enc_type = request.data.get("encounter_type", "OPD")
        chief_complaint = request.data.get("chief_complaint", "").strip()
        notes = request.data.get("notes", "").strip()

        if not chief_complaint:
            return Response(
                {"error": "Chief complaint is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        encounter = Encounter.objects.create(
            patient=patient,
            encounter_type=enc_type,
            chief_complaint=chief_complaint,
            notes=notes,
            created_by=request.user,
            created_at_hospital=request.user.hospital,
        )

        ensure_treatment_relationship(request.user, patient, request.user.hospital)

        log_action(
            request,
            action="CREATE_ENCOUNTER",
            target=encounter,
            patient=patient,
        )

        serializer = EncounterSerializer(encounter, context={"request": request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


# ── Patient Alerts ────────────────────────────────────────────────────────────


class PatientAlertCreateView(APIView):
    """POST /api/patients/<nhid>/alerts/"""

    permission_classes = [IsAuthenticated, IsDoctorOrNurse]

    def post(self, request, universal_id):
        patient = get_object_or_404(Patient, universal_id=universal_id)

        if not can_access_patient(request.user, patient):
            log_action(
                request,
                action="ACCESS_DENIED",
                target=patient,
                patient=patient,
                is_cross_hospital=True,
            )
            return Response({"error": "Access denied."}, status=status.HTTP_403_FORBIDDEN)

        serializer = PatientAlertSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        alert = serializer.save(
            patient=patient,
            recorded_by=request.user,
            recorded_at_hospital=request.user.hospital,
        )

        log_action(
            request,
            action="CREATE_ALERT",
            target=patient,
            patient=patient,
            extra={"kind": alert.kind, "severity": alert.severity},
        )

        return Response(
            PatientAlertSerializer(alert, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class AlertDeactivateView(APIView):
    """POST /api/patients/<nhid>/alerts/<pk>/deactivate/"""

    permission_classes = [IsAuthenticated, IsDoctorOrNurse]

    def post(self, request, universal_id, alert_pk):
        patient = get_object_or_404(Patient, universal_id=universal_id)

        if not can_access_patient(request.user, patient):
            log_action(
                request,
                action="ACCESS_DENIED",
                target=patient,
                patient=patient,
                is_cross_hospital=True,
            )
            return Response({"error": "Access denied."}, status=status.HTTP_403_FORBIDDEN)

        alert = get_object_or_404(PatientAlert, pk=alert_pk, patient=patient)
        alert.is_active = False
        alert.save(update_fields=["is_active"])
        log_action(
            request,
            action="DEACTIVATE_ALERT",
            target=patient,
            patient=patient,
            extra={"alert_pk": alert_pk, "kind": alert.kind},
        )
        return Response({"detail": "Alert deactivated."})
