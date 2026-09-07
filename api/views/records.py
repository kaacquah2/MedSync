"""
Clinical records API views — encounter detail, diagnoses, prescriptions, lab results.

Role enforcement mirrors the template views:
  - doctor + nurse  : create encounters, diagnoses, lab results
  - doctor only     : create prescriptions
  - lab_technician  : create lab results only
"""

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from access.permissions import can_access_patient
from api.permissions import (
    CanAdministerMedication,
    CanCreateEncounter,
    CanCreateLabResult,
    CanPrescribe,
    IsAdminOrClinical,
)
from api.serializers import (
    DiagnosisSerializer,
    EncounterSerializer,
    LabResultSerializer,
    MedicationAdministrationSerializer,
    PrescriptionSerializer,
)
from api.views.vitals import VitalSignSerializer
from audit.utils import log_action
from records.models import (
    Diagnosis,
    Encounter,
    LabResult,
    MedicationAdministration,
    Prescription,
    VitalSign,
)


class EncounterDetailView(APIView):
    """GET /api/encounters/<pk>/"""

    permission_classes = [IsAuthenticated, IsAdminOrClinical]

    def get(self, request, pk):
        encounter = get_object_or_404(
            Encounter.objects.select_related(
                "patient", "created_by", "created_at_hospital"
            ).prefetch_related("diagnoses", "prescriptions", "lab_results"),
            pk=pk,
        )

        if not can_access_patient(request.user, encounter.patient):
            log_action(
                request,
                action="ACCESS_DENIED",
                target=encounter.patient,
                patient=encounter.patient,
                is_cross_hospital=True,
            )
            return Response({"error": "Access denied."}, status=status.HTTP_403_FORBIDDEN)

        is_cross = (
            request.user.hospital is not None
            and encounter.created_at_hospital is not None
            and request.user.hospital_id != encounter.created_at_hospital_id
        )
        log_action(
            request,
            action="VIEW_ENCOUNTER",
            target=encounter,
            patient=encounter.patient,
            is_cross_hospital=is_cross,
        )

        serializer = EncounterSerializer(encounter, context={"request": request})
        data = dict(serializer.data)
        data["is_cross_hospital"] = is_cross
        data["can_prescribe"] = request.user.role == "doctor"
        data["can_add_lab"] = request.user.role in ("doctor", "nurse", "lab_technician")
        data["can_diagnose"] = request.user.role in ("doctor", "nurse")
        return Response(data)


class DiagnosisCreateView(APIView):
    """POST /api/encounters/<pk>/diagnoses/"""

    permission_classes = [IsAuthenticated, CanCreateEncounter]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "record_creation"

    def post(self, request, pk):

        encounter = get_object_or_404(Encounter.objects.select_related("patient"), pk=pk)

        if not can_access_patient(request.user, encounter.patient):
            log_action(
                request,
                action="ACCESS_DENIED",
                target=encounter.patient,
                patient=encounter.patient,
                is_cross_hospital=True,
            )
            return Response({"error": "Access denied."}, status=status.HTTP_403_FORBIDDEN)

        serializer = DiagnosisSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        diagnosis = serializer.save(encounter=encounter, created_by=request.user)

        log_action(
            request,
            action="CREATE_DIAGNOSIS",
            target=diagnosis,
            patient=encounter.patient,
        )
        return Response(
            DiagnosisSerializer(diagnosis).data,
            status=status.HTTP_201_CREATED,
        )


class PrescriptionCreateView(APIView):
    """POST /api/encounters/<pk>/prescriptions/ — doctor only."""

    permission_classes = [IsAuthenticated, CanPrescribe]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "record_creation"

    def post(self, request, pk):
        from api.idempotency import check_idempotency, store_idempotency

        cached_response, cache_key = check_idempotency(request, scope="create_prescription")
        if cached_response:
            return cached_response

        encounter = get_object_or_404(Encounter.objects.select_related("patient"), pk=pk)

        if not can_access_patient(request.user, encounter.patient):
            log_action(
                request,
                action="ACCESS_DENIED",
                target=encounter.patient,
                patient=encounter.patient,
                is_cross_hospital=True,
            )
            store_idempotency(cache_key, None)
            return Response({"error": "Access denied."}, status=status.HTTP_403_FORBIDDEN)

        try:
            serializer = PrescriptionSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            prescription = serializer.save(encounter=encounter, created_by=request.user)
        except Exception:
            store_idempotency(cache_key, None)
            raise

        log_action(
            request,
            action="CREATE_PRESCRIPTION",
            target=prescription,
            patient=encounter.patient,
        )
        res = Response(
            PrescriptionSerializer(prescription).data,
            status=status.HTTP_201_CREATED,
        )
        store_idempotency(cache_key, res)
        return res


class PatientRecordsSummaryView(APIView):
    """
    GET /api/patients/<nhid>/records-summary/

    Returns aggregated diagnoses, prescriptions, lab_results, and vitals
    for a patient across all encounters — used by the patient chart tab system.
    Access-gated exactly like the patient detail view.
    """

    permission_classes = [IsAuthenticated, IsAdminOrClinical]

    def get(self, request, universal_id):
        from patients.models import Patient

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

        encounters = patient.encounters.all()

        diagnoses = (
            Diagnosis.objects.filter(encounter__in=encounters)
            .select_related("created_by", "encounter")
            .order_by("-created_at")
        )
        prescriptions = (
            Prescription.objects.filter(encounter__in=encounters)
            .select_related("created_by", "encounter")
            .order_by("-created_at")
        )
        lab_results = (
            LabResult.objects.filter(encounter__in=encounters)
            .select_related("created_by", "encounter")
            .order_by("-created_at")
        )
        vitals = (
            VitalSign.objects.filter(patient=patient)
            .select_related("recorded_by")
            .order_by("-recorded_at")
        )

        return Response(
            {
                "diagnoses": DiagnosisSerializer(diagnoses, many=True).data,
                "prescriptions": PrescriptionSerializer(prescriptions, many=True).data,
                "lab_results": LabResultSerializer(lab_results, many=True).data,
                "vitals": VitalSignSerializer(vitals, many=True).data,
            }
        )


class LabResultCreateView(APIView):
    """POST /api/encounters/<pk>/lab-results/ — doctor, nurse, or lab_technician."""

    permission_classes = [IsAuthenticated, CanCreateLabResult]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "record_creation"

    def post(self, request, pk):

        encounter = get_object_or_404(Encounter.objects.select_related("patient"), pk=pk)

        if not can_access_patient(request.user, encounter.patient):
            log_action(
                request,
                action="ACCESS_DENIED",
                target=encounter.patient,
                patient=encounter.patient,
                is_cross_hospital=True,
            )
            return Response({"error": "Access denied."}, status=status.HTTP_403_FORBIDDEN)

        serializer = LabResultSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        lab = serializer.save(encounter=encounter, created_by=request.user)

        log_action(
            request,
            action="CREATE_LAB_RESULT",
            target=lab,
            patient=encounter.patient,
        )
        return Response(
            LabResultSerializer(lab).data,
            status=status.HTTP_201_CREATED,
        )


class MedicationAdministrationListView(APIView):
    """
    GET /api/med-admins/?patient=&status=
    """

    permission_classes = [IsAuthenticated, CanAdministerMedication]

    def get(self, request):
        qs = MedicationAdministration.objects.select_related(
            "prescription__encounter__patient",
            "prescription__encounter__created_at_hospital",
            "administered_by",
        ).order_by("scheduled_time")

        patient_nhid = request.GET.get("patient")
        if patient_nhid:
            qs = qs.filter(prescription__encounter__patient__universal_id=patient_nhid)

        status_filter = request.GET.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)

        if request.user.role != "super_admin" and request.user.hospital:
            qs = qs.filter(prescription__encounter__created_at_hospital=request.user.hospital)

        from rest_framework.pagination import PageNumberPagination

        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = MedicationAdministrationSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class MedicationAdministrationUpdateStatusView(APIView):
    """
    PATCH /api/med-admins/<pk>/status/
    """

    permission_classes = [IsAuthenticated, CanAdministerMedication]

    def patch(self, request, pk):
        from django.utils import timezone

        admin = get_object_or_404(MedicationAdministration, pk=pk)

        patient = admin.prescription.encounter.patient
        if not can_access_patient(request.user, patient):
            return Response({"error": "Access denied."}, status=status.HTTP_403_FORBIDDEN)

        new_status = request.data.get("status")
        valid = [s[0] for s in MedicationAdministration.Status.choices]
        if new_status not in valid:
            return Response(
                {"error": f"status must be one of {valid}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        admin.status = new_status
        if new_status == MedicationAdministration.Status.GIVEN:
            admin.administered_by = request.user
            admin.administered_time = timezone.now()
        else:
            admin.administered_by = None
            admin.administered_time = None

        admin.notes = request.data.get("notes", admin.notes)
        admin.save()

        # Audit — `status` in extra captures the full transition so reviewers can
        # distinguish a GIVEN administration from a HELD, MISSED, or CANCELLED rollback.
        log_action(
            request,
            action="ADMINISTER_MEDICATION",
            target=admin,
            patient=admin.prescription.encounter.patient,
            extra={
                "new_status": new_status,
                "administered_by": request.user.username
                if new_status == MedicationAdministration.Status.GIVEN
                else None,
            },
        )

        return Response(MedicationAdministrationSerializer(admin).data)
