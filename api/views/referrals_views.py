"""Referrals API — inter-hospital patient referrals."""

from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from access.permissions import can_access_patient
from api.permissions import CanManageReferrals, has_hospital_access
from audit.utils import log_action
from referrals.models import Referral


class ReferralSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    priority_display = serializers.CharField(source="get_priority_display", read_only=True)
    patient_nhid = serializers.CharField(source="patient.universal_id", read_only=True)
    patient_name = serializers.SerializerMethodField()
    from_hospital_name = serializers.CharField(source="from_hospital.name", read_only=True)
    to_hospital_name = serializers.CharField(source="to_hospital.name", read_only=True)
    from_provider_name = serializers.SerializerMethodField()

    class Meta:
        model = Referral
        fields = [
            "id",
            "patient",
            "patient_nhid",
            "patient_name",
            "from_hospital",
            "from_hospital_name",
            "to_hospital",
            "to_hospital_name",
            "from_provider",
            "from_provider_name",
            "to_provider",
            "reason",
            "priority",
            "priority_display",
            "status",
            "status_display",
            "status_notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "patient_nhid",
            "patient_name",
            "from_hospital_name",
            "to_hospital_name",
            "from_provider_name",
            "status_display",
            "priority_display",
            "created_at",
            "updated_at",
        ]

    def get_patient_name(self, obj):
        try:
            return f"{obj.patient.first_name} {obj.patient.last_name}"
        except Exception:
            return ""

    def get_from_provider_name(self, obj):
        if obj.from_provider:
            return obj.from_provider.get_full_name() or obj.from_provider.username
        return None


class ReferralListCreateView(APIView):
    """
    GET  /api/referrals/  — list referrals (outgoing + incoming for user's hospital)
    POST /api/referrals/  — create a new referral
    """

    permission_classes = [IsAuthenticated, CanManageReferrals]

    def get(self, request):
        if request.user.role == "super_admin":
            qs = Referral.objects.all()
        else:
            hospital = request.user.hospital
            qs = Referral.objects.filter(from_hospital=hospital) | Referral.objects.filter(
                to_hospital=hospital
            )

        direction = request.GET.get("direction")  # "outgoing" or "incoming"
        if direction == "outgoing" and request.user.hospital:
            qs = qs.filter(from_hospital=request.user.hospital)
        elif direction == "incoming" and request.user.hospital:
            qs = qs.filter(to_hospital=request.user.hospital)

        qs = (
            qs.select_related("patient", "from_hospital", "to_hospital", "from_provider")
            .distinct()
            .order_by("-created_at")
        )

        from rest_framework.pagination import PageNumberPagination

        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(qs, request)
        data = ReferralSerializer(page, many=True).data
        extra = {"count": len(data)}
        if direction:
            extra["direction"] = direction
        log_action(
            request,
            action="VIEW_REFERRALS",
            target=getattr(request.user, "hospital", None),
            extra=extra,
        )
        return paginator.get_paginated_response(data)

    def post(self, request):
        patient_nhid = request.data.get("patient_nhid") or request.data.get("patient")
        from patients.models import Patient

        patient = (
            get_object_or_404(Patient, universal_id=patient_nhid)
            if isinstance(patient_nhid, str) and patient_nhid.startswith("NHID")
            else get_object_or_404(Patient, pk=patient_nhid)
        )

        if not can_access_patient(request.user, patient):
            log_action(
                request,
                action="ACCESS_DENIED",
                target=patient,
                patient=patient,
                is_cross_hospital=True,
            )
            return Response({"error": "Access denied."}, status=status.HTTP_403_FORBIDDEN)

        serializer = ReferralSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        referral = serializer.save(
            patient=patient,
            from_hospital=request.user.hospital,
            from_provider=request.user,
        )
        log_action(
            request,
            action="CREATE_REFERRAL",
            target=referral,
            patient=patient,
            extra={
                "to_hospital": referral.to_hospital.code,
                "priority": referral.priority,
            },
        )
        return Response(ReferralSerializer(referral).data, status=status.HTTP_201_CREATED)


class ReferralStatusView(APIView):
    """PATCH /api/referrals/<pk>/status/ — accept/reject/complete a referral."""

    permission_classes = [IsAuthenticated, CanManageReferrals]

    def patch(self, request, pk):
        referral = get_object_or_404(Referral, pk=pk)
        if not has_hospital_access(request.user, [referral.from_hospital, referral.to_hospital]):
            return Response({"error": "Access denied."}, status=status.HTTP_403_FORBIDDEN)

        new_status = request.data.get("status")
        notes = request.data.get("status_notes", "")

        valid = [s[0] for s in Referral.Status.choices]
        if new_status not in valid:
            return Response(
                {"error": f"status must be one of {valid}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        referral.status = new_status
        referral.status_notes = notes
        referral.save(update_fields=["status", "status_notes"])

        if new_status == Referral.Status.ACCEPTED:
            from access.permissions import ensure_treatment_relationship
            from_name = referral.from_hospital.name if referral.from_hospital else "external hospital"
            reason = f"Accepted referral from {from_name}"
            if referral.reason:
                reason += f": {referral.reason}"
            ensure_treatment_relationship(
                clinician=request.user,
                patient=referral.patient,
                hospital=referral.to_hospital,
                reason=reason,
            )

        log_action(
            request,
            action="UPDATE_REFERRAL",
            target=referral,
            patient=referral.patient,
            extra={"new_status": new_status},
        )
        return Response(ReferralSerializer(referral).data)
