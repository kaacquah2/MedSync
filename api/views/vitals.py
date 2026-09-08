"""Vital signs API — record and retrieve patient vitals."""

from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from access.permissions import can_access_patient
from api.permissions import CanRecordVitals
from audit.utils import log_action
from patients.models import Patient
from records.models import VitalSign


class VitalSignSerializer(serializers.ModelSerializer):
    recorded_by_name = serializers.SerializerMethodField()

    class Meta:
        model = VitalSign
        fields = [
            "id",
            "encounter",
            "recorded_by",
            "recorded_by_name",
            "recorded_at",
            "temperature",
            "heart_rate",
            "respiratory_rate",
            "bp_systolic",
            "bp_diastolic",
            "spo2",
            "pain_score",
            "weight_kg",
            "height_cm",
            "blood_glucose",
            "created_at",
        ]
        read_only_fields = ["id", "recorded_by", "recorded_by_name", "created_at"]
        extra_kwargs = {
            "temperature": {
                "validators": [
                    MinValueValidator(Decimal("30.0")),
                    MaxValueValidator(Decimal("45.0")),
                ]
            },
            "heart_rate": {
                "validators": [
                    MinValueValidator(20),
                    MaxValueValidator(300),
                ]
            },
            "bp_systolic": {
                "validators": [
                    MinValueValidator(50),
                    MaxValueValidator(250),
                ]
            },
            "bp_diastolic": {
                "validators": [
                    MinValueValidator(30),
                    MaxValueValidator(150),
                ]
            },
            "spo2": {
                "validators": [
                    MinValueValidator(Decimal("50.0")),
                    MaxValueValidator(Decimal("100.0")),
                ]
            },
            "pain_score": {
                "validators": [
                    MinValueValidator(0),
                    MaxValueValidator(10),
                ]
            },
            "respiratory_rate": {
                "validators": [
                    MinValueValidator(4),
                    MaxValueValidator(80),
                ]
            },
            "weight_kg": {
                "validators": [
                    MinValueValidator(Decimal("0.5")),
                    MaxValueValidator(Decimal("500.0")),
                ]
            },
            "height_cm": {
                "validators": [
                    MinValueValidator(Decimal("20.0")),
                    MaxValueValidator(Decimal("300.0")),
                ]
            },
            "blood_glucose": {
                "validators": [
                    MinValueValidator(Decimal("0.5")),
                    MaxValueValidator(Decimal("50.0")),
                ]
            },
        }

    def get_recorded_by_name(self, obj):
        if obj.recorded_by:
            return obj.recorded_by.get_full_name() or obj.recorded_by.username
        return None

    def validate(self, attrs):
        attrs = super().validate(attrs)
        systolic = attrs.get("bp_systolic")
        if systolic is None and self.instance:
            systolic = self.instance.bp_systolic
        diastolic = attrs.get("bp_diastolic")
        if diastolic is None and self.instance:
            diastolic = self.instance.bp_diastolic

        if systolic is not None and diastolic is not None and systolic <= diastolic:
            raise serializers.ValidationError(
                {
                    "bp_systolic": "Systolic blood pressure must be greater than diastolic blood pressure."
                }
            )
        return attrs


class PatientVitalListCreateView(APIView):
    """
    GET  /api/patients/<nhid>/vitals/   — list vitals (access-gated)
    POST /api/patients/<nhid>/vitals/   — record new vitals (doctor/nurse)
    """

    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), CanRecordVitals()]
        return [IsAuthenticated()]

    def get_throttles(self):
        if self.request.method == "POST":
            self.throttle_scope = "record_creation"
            return [ScopedRateThrottle()]
        return []

    def _get_patient(self, request, universal_id):
        patient = get_object_or_404(Patient, universal_id=universal_id)
        decision = can_access_patient(request.user, patient)
        return patient, decision

    def get(self, request, universal_id):
        patient, decision = self._get_patient(request, universal_id)
        if not decision:
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

        from rest_framework.pagination import PageNumberPagination

        qs = patient.vitals.select_related("recorded_by", "encounter").order_by("-recorded_at")
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(VitalSignSerializer(page, many=True).data)

    def post(self, request, universal_id):

        patient, decision = self._get_patient(request, universal_id)
        if not decision:
            log_action(
                request,
                action="ACCESS_DENIED",
                target=patient,
                patient=patient,
                is_cross_hospital=True,
            )
            return Response({"error": "Access denied."}, status=status.HTTP_403_FORBIDDEN)

        serializer = VitalSignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vital = serializer.save(
            patient=patient,
            recorded_by=request.user,
        )
        log_action(request, action="CREATE_VITAL", target=vital, patient=patient)
        return Response(VitalSignSerializer(vital).data, status=status.HTTP_201_CREATED)
