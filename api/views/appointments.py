"""Appointments API — scheduling and status management."""

from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from api.permissions import CanManageAppointments
from audit.utils import log_action
from scheduling.models import Appointment


class AppointmentSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    appointment_type_display = serializers.CharField(
        source="get_appointment_type_display", read_only=True
    )
    triage_acuity_display = serializers.CharField(
        source="get_triage_acuity_display", read_only=True
    )
    triage_level = serializers.CharField(source="triage_acuity", read_only=True)
    patient_nhid = serializers.CharField(source="patient.universal_id", read_only=True)
    patient_name = serializers.SerializerMethodField()
    provider_name = serializers.SerializerMethodField()
    hospital_name = serializers.CharField(source="hospital.name", read_only=True)

    class Meta:
        model = Appointment
        fields = [
            "id",
            "patient",
            "patient_nhid",
            "patient_name",
            "provider",
            "provider_name",
            "hospital",
            "hospital_name",
            "scheduled_for",
            "duration_minutes",
            "appointment_type",
            "appointment_type_display",
            "status",
            "status_display",
            "triage_acuity",
            "triage_acuity_display",
            "triage_level",
            "reason",
            "notes",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "patient_nhid",
            "patient_name",
            "provider_name",
            "hospital_name",
            "status_display",
            "appointment_type_display",
            "triage_acuity_display",
            "triage_level",
            "created_at",
        ]

    def to_internal_value(self, data):
        if hasattr(data, "copy"):
            data = data.copy()
        elif isinstance(data, dict):
            data = dict(data)
        if isinstance(data, dict):
            if "triage_level" in data and "triage_acuity" not in data:
                data["triage_acuity"] = data["triage_level"]
        return super().to_internal_value(data)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        appt_type = attrs.get("appointment_type")
        if appt_type is None and self.instance:
            appt_type = self.instance.appointment_type

        triage_acuity = attrs.get("triage_acuity")
        if triage_acuity is None and self.instance:
            triage_acuity = self.instance.triage_acuity

        if appt_type == Appointment.AppointmentType.EMERGENCY and not triage_acuity:
            raise serializers.ValidationError(
                {"triage_acuity": "Triage acuity (RED, ORANGE, YELLOW, GREEN) is mandatory for emergency appointments."}
            )
        return attrs

    def get_patient_name(self, obj):
        try:
            return f"{obj.patient.first_name} {obj.patient.last_name}"
        except Exception:
            return ""

    def get_provider_name(self, obj):
        if obj.provider:
            return obj.provider.get_full_name() or obj.provider.username
        return None


class AppointmentListCreateView(APIView):
    """
    GET  /api/appointments/  — list appointments for user's hospital
    POST /api/appointments/  — create a new appointment
    """

    permission_classes = [IsAuthenticated, CanManageAppointments]

    def get(self, request):
        qs = Appointment.objects.select_related("patient", "provider", "hospital")
        # Scope by hospital (super_admin sees all)
        if request.user.role != "super_admin":
            qs = qs.filter(hospital=request.user.hospital)

        # Optional date filter
        date_str = request.GET.get("date")
        if date_str:
            qs = qs.filter(scheduled_for__date=date_str)

        # Status filter
        appt_status = request.GET.get("status")
        if appt_status:
            qs = qs.filter(status=appt_status)

        # Appointment type filter
        appt_type = request.GET.get("appointment_type")
        if appt_type:
            qs = qs.filter(appointment_type=appt_type)

        # Triage acuity filter
        triage_acuity = request.GET.get("triage_acuity")
        if triage_acuity:
            qs = qs.filter(triage_acuity=triage_acuity)

        qs = qs.order_by("scheduled_for")
        data = AppointmentSerializer(qs, many=True).data
        extra = {"count": len(data)}
        if date_str:
            extra["date"] = date_str
        if appt_status:
            extra["status"] = appt_status
        if appt_type:
            extra["appointment_type"] = appt_type
        if triage_acuity:
            extra["triage_acuity"] = triage_acuity
        log_action(
            request,
            action="VIEW_APPOINTMENTS",
            target=getattr(request.user, "hospital", None),
            extra=extra,
        )
        return Response(data)

    def post(self, request):
        data = request.data.copy()
        if "hospital" not in data and getattr(request.user, "hospital", None):
            data["hospital"] = request.user.hospital.pk

        patient_val = data.get("patient")
        if isinstance(patient_val, str) and patient_val.startswith("NHID-"):
            from patients.models import Patient

            patient_obj = Patient.objects.filter(universal_id=patient_val).first()
            if patient_obj:
                data["patient"] = patient_obj.pk
            else:
                return Response(
                    {"error": f"Patient with NHID {patient_val} not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )

        serializer = AppointmentSerializer(data=data)
        serializer.is_valid(raise_exception=True)

        if request.user.role != "super_admin":
            supplied = serializer.validated_data.get("hospital")
            if supplied and supplied != request.user.hospital:
                return Response(
                    {"error": "You can only create appointments for your own hospital."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        appt = serializer.save(created_by=request.user)
        log_action(
            request,
            action="CREATE_APPOINTMENT",
            target=appt,
            patient=appt.patient,
            extra={"scheduled_for": appt.scheduled_for.isoformat()},
        )
        return Response(AppointmentSerializer(appt).data, status=status.HTTP_201_CREATED)


class AppointmentDetailView(APIView):
    """GET/PATCH /api/appointments/<pk>/"""

    permission_classes = [IsAuthenticated, CanManageAppointments]

    def get(self, request, pk):
        appt = self._get_appt(request, pk)
        is_cross = (
            request.user.hospital is not None
            and appt.hospital is not None
            and request.user.hospital_id != appt.hospital_id
        )
        log_action(
            request,
            action="VIEW_APPOINTMENT",
            target=appt,
            patient=appt.patient,
            is_cross_hospital=is_cross,
        )
        return Response(AppointmentSerializer(appt).data)

    def patch(self, request, pk):
        appt = self._get_appt(request, pk)
        serializer = AppointmentSerializer(appt, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        appt = serializer.save()
        log_action(
            request,
            action="UPDATE_APPOINTMENT",
            target=appt,
            patient=appt.patient,
            extra={"status": appt.status},
        )
        return Response(AppointmentSerializer(appt).data)

    def _get_appt(self, request, pk):
        appt = get_object_or_404(Appointment, pk=pk)
        if request.user.role != "super_admin" and appt.hospital != request.user.hospital:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("Appointment belongs to a different hospital.")
        return appt


class AppointmentStatusView(APIView):
    """POST /api/appointments/<pk>/status/ — quick status transition (check-in, no-show)."""

    permission_classes = [IsAuthenticated, CanManageAppointments]

    VALID_TRANSITIONS = {
        "check_in": ("scheduled",),
        "start": ("checked_in",),
        "complete": ("in_progress",),
        "no_show": ("scheduled", "checked_in"),
        "cancel": ("scheduled", "checked_in"),
    }
    ACTION_STATUS = {
        "check_in": "checked_in",
        "start": "in_progress",
        "complete": "completed",
        "no_show": "no_show",
        "cancel": "cancelled",
    }

    def post(self, request, pk):
        appt = get_object_or_404(Appointment, pk=pk)
        if request.user.role != "super_admin" and appt.hospital != request.user.hospital:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("Appointment belongs to a different hospital.")
        action = request.data.get("action")

        if action not in self.VALID_TRANSITIONS:
            return Response(
                {"error": f"action must be one of {list(self.VALID_TRANSITIONS)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if appt.status not in self.VALID_TRANSITIONS[action]:
            return Response(
                {"error": f"Cannot '{action}' an appointment with status '{appt.status}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        appt.status = self.ACTION_STATUS[action]
        appt.save(update_fields=["status"])
        log_action(
            request,
            action="UPDATE_APPOINTMENT",
            target=appt,
            patient=appt.patient,
            extra={"transition": action, "new_status": appt.status},
        )
        return Response(AppointmentSerializer(appt).data)
