"""
Clinical records API views — encounter detail, diagnoses, prescriptions, lab results.

Role enforcement mirrors the template views:
  - doctor + nurse  : create encounters, diagnoses, lab results
  - doctor only     : create prescriptions
  - lab_technician  : create lab results only
"""

from django.core.mail import send_mail
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
    CanDiagnose,
    CanPrescribe,
    IsAdminOrClinical,
    IsDoctorOrNurse,
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
from patients.models import PatientAlert
from records.models import (
    Diagnosis,
    Encounter,
    LabOrder,
    LabResult,
    MedicationAdministration,
    Prescription,
    VitalSign,
)


class EncounterDetailView(APIView):
    """GET /api/encounters/<pk>/ — doctor and nurse only."""

    permission_classes = [IsAuthenticated, IsDoctorOrNurse]

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
        data["can_add_lab"] = request.user.role == "lab_technician"
        data["can_diagnose"] = request.user.role == "doctor"
        return Response(data)


class DiagnosisCreateView(APIView):
    """POST /api/encounters/<pk>/diagnoses/ — doctor only."""

    permission_classes = [IsAuthenticated, CanDiagnose]
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

        drug_name = str(request.data.get("drug_name") or "").strip()
        rxnorm_code = request.data.get("rxnorm_code")
        override_reason = str(request.data.get("allergy_override_reason") or "").strip()

        from records.allergy_checker import check_prescription_allergies

        conflicts = check_prescription_allergies(encounter.patient, drug_name, rxnorm_code=rxnorm_code)
        if conflicts:
            if not override_reason or len(override_reason) < 10:
                conflict_details = [
                    {
                        "allergy_id": c.allergy_id,
                        "allergy_label": c.allergy_label,
                        "severity": c.severity,
                        "reaction": c.reaction,
                        "drug_prescribed": c.drug_prescribed,
                        "conflict_type": c.conflict_type,
                        "message": c.message,
                    }
                    for c in conflicts
                ]
                store_idempotency(cache_key, None)
                return Response(
                    {
                        "error": "ALLERGY_CONFLICT",
                        "detail": (
                            f"Prescription of '{drug_name}' conflicts with documented allergy: "
                            f"{conflicts[0].allergy_label} ({conflicts[0].severity}). "
                            "A mandatory clinical override justification (minimum 10 characters) is required."
                        ),
                        "conflicts": conflict_details,
                    },
                    status=status.HTTP_409_CONFLICT,
                )

        try:
            serializer = PrescriptionSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            prescription = serializer.save(encounter=encounter, created_by=request.user)
        except Exception:
            store_idempotency(cache_key, None)
            raise

        extra_audit = {}
        if conflicts and override_reason:
            extra_audit["allergy_override"] = True
            extra_audit["conflicts"] = [
                {"allergy": c.allergy_label, "severity": c.severity, "type": c.conflict_type}
                for c in conflicts
            ]
            extra_audit["override_reason"] = override_reason

        log_action(
            request,
            action="CREATE_PRESCRIPTION",
            target=prescription,
            patient=encounter.patient,
            extra=extra_audit or None,
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

        user_role = getattr(request.user, "role", "")
        can_view_clinical = user_role in ("doctor", "nurse")

        return Response(
            {
                "diagnoses": DiagnosisSerializer(diagnoses, many=True).data if can_view_clinical else [],
                "prescriptions": PrescriptionSerializer(prescriptions, many=True).data if can_view_clinical else [],
                "lab_results": LabResultSerializer(lab_results, many=True).data if (can_view_clinical or user_role == "lab_technician") else [],
                "vitals": VitalSignSerializer(vitals, many=True).data if (can_view_clinical or getattr(request.user, "is_admin_level", False)) else [],
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

        is_critical_flag = (
            serializer.validated_data.get("is_critical", False)
            or serializer.validated_data.get("notify_doctor", False)
        )
        if is_critical_flag:
            serializer.validated_data["is_critical"] = True
            serializer.validated_data["is_abnormal"] = True

        notify_doctor = serializer.validated_data.pop("notify_doctor", False)
        lab = serializer.save(encounter=encounter, created_by=request.user)

        # If originating LabOrder was linked, mark it as resulted
        if lab.order:
            lab.order.status = LabOrder.Status.RESULTED
            lab.order.save(update_fields=["status"])
            log_action(
                request,
                action="UPDATE_LAB_ORDER",
                target=lab.order,
                patient=encounter.patient,
                extra={"status": LabOrder.Status.RESULTED, "result_id": lab.pk},
            )

        doctor_notified = False
        doctor_name = None
        patient_alert = None

        if lab.is_critical:
            # 1. Create PatientAlert visible across all facilities and on emergency feeds
            patient_alert = PatientAlert.objects.create(
                patient=encounter.patient,
                kind=PatientAlert.Kind.ALERT,
                label=f"CRITICAL LAB: {lab.test_name}",
                severity=PatientAlert.Severity.LIFE_THREAT,
                reaction=f"Value: {lab.result_value}. Reference: {lab.reference_range or 'N/A'}",
                recorded_by=request.user,
                recorded_at_hospital=encounter.created_at_hospital,
                is_active=True,
            )
            log_action(
                request,
                action="CREATE_ALERT",
                target=encounter.patient,
                patient=encounter.patient,
                extra={
                    "kind": patient_alert.kind,
                    "severity": patient_alert.severity,
                    "lab_result_id": lab.pk,
                    "is_critical": True,
                },
            )

            # 2. Dispatch urgent notification to ordering / attending physician
            ordering_doc = (lab.order.ordered_by if lab.order else None) or encounter.created_by
            if ordering_doc:
                doctor_name = ordering_doc.get_full_name() or ordering_doc.username
                if ordering_doc.email:
                    subject = f"URGENT: Critical Lab Value Alert — {lab.test_name} (Patient {encounter.patient.universal_id})"
                    message = (
                        f"URGENT CLINICAL ALERT\n\n"
                        f"A critical laboratory result has been reported for your patient:\n"
                        f"Patient NHID: {encounter.patient.universal_id}\n"
                        f"Patient Name: {encounter.patient.first_name} {encounter.patient.last_name}\n"
                        f"Test: {lab.test_name}\n"
                        f"Result: {lab.result_value}\n"
                        f"Reference Range: {lab.reference_range or 'N/A'}\n"
                        f"Reported by: {request.user.get_full_name() or request.user.username} (Lab Tech)\n"
                        f"Timestamp: {lab.created_at.isoformat()}\n\n"
                        f"Please log into mEd immediately to review the patient's record and take clinical action."
                    )
                    try:
                        send_mail(
                            subject=subject,
                            message=message,
                            from_email=None,
                            recipient_list=[ordering_doc.email],
                            fail_silently=True,
                        )
                        doctor_notified = True
                    except Exception:
                        doctor_notified = False
                else:
                    doctor_notified = True

        lab._doctor_notified = doctor_notified
        lab._doctor_name = doctor_name
        lab._patient_alert_id = patient_alert.pk if patient_alert else None

        log_action(
            request,
            action="CREATE_LAB_RESULT",
            target=lab,
            patient=encounter.patient,
            extra={
                "is_critical": lab.is_critical,
                "is_abnormal": lab.is_abnormal,
                "doctor_notified": doctor_notified,
                "ordering_doctor": doctor_name,
                "patient_alert_id": lab._patient_alert_id,
            },
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
        data = serializer.data

        patient_obj = None
        is_cross = False
        if patient_nhid:
            from patients.models import Patient

            patient_obj = Patient.objects.filter(universal_id=patient_nhid).first()
            if (
                patient_obj
                and request.user.hospital is not None
                and patient_obj.registered_at_hospital is not None
                and request.user.hospital_id != patient_obj.registered_at_hospital_id
            ):
                is_cross = True

        extra = {"count": len(data)}
        if status_filter:
            extra["status"] = status_filter
        if patient_nhid:
            extra["patient_nhid"] = patient_nhid

        log_action(
            request,
            action="VIEW_MAR",
            target=patient_obj or getattr(request.user, "hospital", None),
            patient=patient_obj,
            is_cross_hospital=is_cross,
            extra=extra,
        )

        return paginator.get_paginated_response(data)


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
