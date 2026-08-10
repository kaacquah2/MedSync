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
            "created_at",
        ]

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

        qs = qs.order_by("scheduled_for")
        return Response(AppointmentSerializer(qs, many=True).data)

    def post(self, request):
        data = request.data.copy()
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

        # Default hospital to user's hospital if not provided
        if "hospital" not in request.data and request.user.hospital:
            serializer.validated_data["hospital"] = request.user.hospital
        elif request.user.role != "super_admin":
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
