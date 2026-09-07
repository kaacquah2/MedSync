"""Wards & Beds API — facility management."""

from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from api.permissions import CanManageWards, has_hospital_access
from hospitals.models import Bed, Ward


class BedSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    patient_nhid = serializers.CharField(
        source="current_patient.universal_id", read_only=True, allow_null=True
    )

    class Meta:
        model = Bed
        fields = [
            "id",
            "label",
            "status",
            "status_display",
            "patient_nhid",
            "created_at",
        ]
        read_only_fields = ["id", "status_display", "patient_nhid", "created_at"]


class WardSerializer(serializers.ModelSerializer):
    beds = BedSerializer(many=True, read_only=True)
    occupied_count = serializers.IntegerField(read_only=True)
    available_count = serializers.IntegerField(read_only=True)
    hospital_name = serializers.CharField(source="hospital.name", read_only=True)

    class Meta:
        model = Ward
        fields = [
            "id",
            "hospital",
            "hospital_name",
            "name",
            "code",
            "capacity",
            "occupied_count",
            "available_count",
            "beds",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "hospital_name",
            "occupied_count",
            "available_count",
            "beds",
            "created_at",
        ]


class WardListCreateView(APIView):
    """
    GET  /api/wards/   — list wards for hospital
    POST /api/wards/   — create a ward (hospital_admin/super_admin)
    """

    permission_classes = [IsAuthenticated, CanManageWards]

    def get(self, request):
        qs = Ward.objects.prefetch_related("beds__current_patient").select_related("hospital")
        if request.user.role != "super_admin" and not getattr(request.user, "is_superuser", False):
            qs = qs.filter(hospital=request.user.hospital)
        hospital_id = request.GET.get("hospital")
        if hospital_id:
            qs = qs.filter(hospital_id=hospital_id)
        return Response(WardSerializer(qs, many=True).data)

    def post(self, request):
        serializer = WardSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if "hospital" not in request.data and request.user.hospital:
            serializer.validated_data["hospital"] = request.user.hospital
        elif request.user.role != "super_admin" and not getattr(
            request.user, "is_superuser", False
        ):
            supplied = serializer.validated_data.get("hospital")
            if supplied and supplied != request.user.hospital:
                return Response(
                    {"error": "You can only create wards for your own hospital."},
                    status=status.HTTP_403_FORBIDDEN,
                )
        ward = serializer.save()
        return Response(WardSerializer(ward).data, status=status.HTTP_201_CREATED)


class WardDetailView(APIView):
    """GET/PATCH /api/wards/<pk>/"""

    permission_classes = [IsAuthenticated, CanManageWards]

    def get(self, request, pk):
        ward = get_object_or_404(Ward, pk=pk)
        return Response(WardSerializer(ward).data)

    def patch(self, request, pk):
        ward = get_object_or_404(Ward, pk=pk)
        if (
            request.user.role != "super_admin"
            and not getattr(request.user, "is_superuser", False)
            and ward.hospital != request.user.hospital
        ):
            return Response({"error": "Access denied."}, status=status.HTTP_403_FORBIDDEN)
        serializer = WardSerializer(ward, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        ward = serializer.save()
        return Response(WardSerializer(ward).data)


class BedStatusView(APIView):
    """PATCH /api/beds/<pk>/status/ — update a bed's availability status."""

    permission_classes = [IsAuthenticated, CanManageWards]

    def patch(self, request, pk):
        bed = get_object_or_404(Bed, pk=pk)
        if not has_hospital_access(request.user, bed.ward.hospital):
            return Response({"error": "Access denied."}, status=status.HTTP_403_FORBIDDEN)

        new_status = request.data.get("status")
        valid = [s[0] for s in Bed.Status.choices]
        if new_status not in valid:
            return Response(
                {"error": f"status must be one of {valid}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        bed.status = new_status
        if new_status != Bed.Status.OCCUPIED:
            bed.current_patient = None
        bed.save(update_fields=["status", "current_patient"])
        return Response(BedSerializer(bed).data)
