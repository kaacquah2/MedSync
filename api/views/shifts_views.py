"""Shifts API — nurse shift records and handover notes."""

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from api.permissions import CanManageShifts, has_hospital_access
from audit.utils import log_action
from shifts.models import Handover, ShiftRecord


class ShiftSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    ward_name = serializers.SerializerMethodField()
    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = ShiftRecord
        fields = [
            "id",
            "user",
            "user_name",
            "ward",
            "ward_name",
            "started_at",
            "ended_at",
            "break_minutes",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["id", "user", "user_name", "ward_name", "is_active", "created_at"]

    def get_user_name(self, obj):
        return obj.user.get_full_name() or obj.user.username

    def get_ward_name(self, obj):
        return str(obj.ward) if obj.ward else None


class HandoverSerializer(serializers.ModelSerializer):
    from_user_name = serializers.SerializerMethodField()
    to_user_name = serializers.SerializerMethodField()
    ward_name = serializers.SerializerMethodField()
    acknowledged_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Handover
        fields = [
            "id",
            "shift",
            "from_user",
            "from_user_name",
            "to_user",
            "to_user_name",
            "ward",
            "ward_name",
            "summary",
            "acknowledged_by",
            "acknowledged_by_name",
            "acknowledged_at",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "from_user",
            "from_user_name",
            "acknowledged_by",
            "acknowledged_by_name",
            "acknowledged_at",
            "created_at",
        ]

    def get_from_user_name(self, obj):
        return obj.from_user.get_full_name() or obj.from_user.username

    def get_to_user_name(self, obj):
        if obj.to_user:
            return obj.to_user.get_full_name() or obj.to_user.username
        return None

    def get_ward_name(self, obj):
        return str(obj.ward) if obj.ward else None

    def get_acknowledged_by_name(self, obj):
        if obj.acknowledged_by:
            return obj.acknowledged_by.get_full_name() or obj.acknowledged_by.username
        return None


class ShiftListView(APIView):
    """GET /api/shifts/ — list shifts for user's hospital."""

    permission_classes = [IsAuthenticated, CanManageShifts]

    def get(self, request):
        qs = ShiftRecord.objects.select_related("user", "ward")
        if request.user.role == "nurse":
            qs = qs.filter(user=request.user)
        elif request.user.role not in ("super_admin",):
            qs = qs.filter(user__hospital=request.user.hospital)
        limit = min(int(request.query_params.get("limit", 200)), 500)
        return Response(ShiftSerializer(qs.order_by("-started_at")[:limit], many=True).data)


class ShiftStartView(APIView):
    """POST /api/shifts/start/ — nurse starts a shift."""

    permission_classes = [IsAuthenticated, CanManageShifts]

    def post(self, request):
        # Close any open shift first
        open_shift = ShiftRecord.objects.filter(user=request.user, ended_at__isnull=True).first()
        if open_shift:
            return Response(
                {"error": "You already have an active shift. End it before starting a new one."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = ShiftSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        shift = serializer.save(user=request.user)
        log_action(request, action="START_SHIFT", target=shift)
        return Response(ShiftSerializer(shift).data, status=status.HTTP_201_CREATED)


class ShiftEndView(APIView):
    """PATCH /api/shifts/<pk>/end/ — end an active shift."""

    permission_classes = [IsAuthenticated, CanManageShifts]

    def patch(self, request, pk):
        shift = get_object_or_404(ShiftRecord, pk=pk)

        if request.user.role == "nurse" and shift.user != request.user:
            return Response(
                {"error": "You can only end your own shift."}, status=status.HTTP_403_FORBIDDEN
            )

        if not has_hospital_access(request.user, shift.user.hospital):
            return Response({"error": "Access denied."}, status=status.HTTP_403_FORBIDDEN)

        if shift.ended_at:
            return Response({"error": "Shift already ended."}, status=status.HTTP_400_BAD_REQUEST)

        break_minutes = request.data.get("break_minutes", shift.break_minutes)
        shift.ended_at = timezone.now()
        shift.break_minutes = break_minutes
        shift.save(update_fields=["ended_at", "break_minutes"])
        log_action(request, action="END_SHIFT", target=shift)
        return Response(ShiftSerializer(shift).data)


class HandoverListCreateView(APIView):
    """
    GET  /api/handovers/  — list handovers for user's ward/hospital
    POST /api/handovers/  — create a handover note
    """

    permission_classes = [IsAuthenticated, CanManageShifts]

    def get(self, request):
        qs = Handover.objects.select_related("from_user", "to_user", "ward")
        if request.user.role == "nurse":
            qs = qs.filter(from_user__hospital=request.user.hospital)
        elif request.user.role not in ("super_admin",):
            qs = qs.filter(from_user__hospital=request.user.hospital)
        limit = min(int(request.query_params.get("limit", 100)), 500)
        data = HandoverSerializer(qs.order_by("-created_at")[:limit], many=True).data
        log_action(
            request,
            action="VIEW_HANDOVERS",
            target=getattr(request.user, "hospital", None),
            extra={"count": len(data), "limit": limit},
        )
        return Response(data)

    def post(self, request):
        serializer = HandoverSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        handover = serializer.save(from_user=request.user)
        log_action(request, action="CREATE_HANDOVER", target=handover)
        return Response(HandoverSerializer(handover).data, status=status.HTTP_201_CREATED)


class HandoverAcknowledgeView(APIView):
    """PATCH /api/handovers/<pk>/acknowledge/ — record incoming nurse acknowledgement."""

    permission_classes = [IsAuthenticated, CanManageShifts]

    def patch(self, request, pk):
        handover = get_object_or_404(Handover, pk=pk)
        allowed_hospitals = [
            h
            for h in [
                getattr(handover.from_user, "hospital", None),
                getattr(handover.to_user, "hospital", None) if handover.to_user else None,
                getattr(handover.ward, "hospital", None) if handover.ward else None,
            ]
            if h is not None
        ]
        if not has_hospital_access(request.user, allowed_hospitals):
            return Response({"error": "Access denied."}, status=status.HTTP_403_FORBIDDEN)

        if handover.acknowledged_at:
            return Response(HandoverSerializer(handover).data)
        handover.acknowledged_by = request.user
        handover.acknowledged_at = timezone.now()
        handover.save(update_fields=["acknowledged_by", "acknowledged_at"])
        log_action(request, action="ACKNOWLEDGE_HANDOVER", target=handover)
        return Response(HandoverSerializer(handover).data)
