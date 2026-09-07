"""Lab orders API — order management workflow."""

from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from access.permissions import can_access_patient
from api.permissions import CanOrderLabTest, CanResultLabOrder
from audit.utils import log_action
from patients.models import Patient
from records.models import LabOrder
from records.validators import validate_loinc


class LabOrderSerializer(serializers.ModelSerializer):
    ordered_by_name = serializers.SerializerMethodField()
    patient_nhid = serializers.CharField(source="patient.universal_id", read_only=True)
    priority_display = serializers.CharField(source="get_priority_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    loinc_code = serializers.CharField(
        required=False, allow_blank=True, validators=[validate_loinc]
    )

    class Meta:
        model = LabOrder
        fields = [
            "id",
            "encounter",
            "patient_nhid",
            "ordered_by",
            "ordered_by_name",
            "test_name",
            "loinc_code",
            "priority",
            "priority_display",
            "status",
            "status_display",
            "clinical_notes",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "ordered_by",
            "ordered_by_name",
            "patient_nhid",
            "created_at",
            "priority_display",
            "status_display",
        ]

    def get_ordered_by_name(self, obj):
        if obj.ordered_by:
            return obj.ordered_by.get_full_name() or obj.ordered_by.username
        return None


class PatientLabOrderListCreateView(APIView):
    """
    GET  /api/patients/<nhid>/lab-orders/  — list orders (access-gated)
    POST /api/patients/<nhid>/lab-orders/  — place a new order (doctor/nurse)
    """

    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), CanOrderLabTest()]
        return [IsAuthenticated()]

    def get_throttles(self):
        if self.request.method == "POST":
            self.throttle_scope = "record_creation"
            return [ScopedRateThrottle()]
        return []

    def _get_patient(self, request, universal_id):
        patient = get_object_or_404(Patient, universal_id=universal_id)
        return patient, can_access_patient(request.user, patient)

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

        from rest_framework.pagination import PageNumberPagination

        qs = patient.lab_orders.select_related("ordered_by").order_by("-created_at")
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(LabOrderSerializer(page, many=True).data)

    def post(self, request, universal_id):
        from api.idempotency import check_idempotency, store_idempotency

        cached_response, cache_key = check_idempotency(request, scope="create_lab_order")
        if cached_response:
            return cached_response

        patient, decision = self._get_patient(request, universal_id)
        if not decision:
            log_action(
                request,
                action="ACCESS_DENIED",
                target=patient,
                patient=patient,
                is_cross_hospital=True,
            )
            store_idempotency(cache_key, None)
            return Response({"error": "Access denied."}, status=status.HTTP_403_FORBIDDEN)

        try:
            serializer = LabOrderSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            order = serializer.save(patient=patient, ordered_by=request.user)
        except Exception:
            store_idempotency(cache_key, None)
            raise

        log_action(request, action="CREATE_LAB_ORDER", target=order, patient=patient)
        res = Response(LabOrderSerializer(order).data, status=status.HTTP_201_CREATED)
        store_idempotency(cache_key, res)
        return res


class LabOrderDetailView(APIView):
    """
    GET   /api/lab-orders/<pk>/         — view order
    PATCH /api/lab-orders/<pk>/status/  — update status (lab_technician)
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        order = get_object_or_404(LabOrder, pk=pk)
        if not can_access_patient(request.user, order.patient):
            log_action(
                request,
                action="ACCESS_DENIED",
                target=order.patient,
                patient=order.patient,
                is_cross_hospital=True,
            )
            return Response({"error": "Access denied."}, status=status.HTTP_403_FORBIDDEN)
        return Response(LabOrderSerializer(order).data)


class LabOrderStatusView(APIView):
    """PATCH /api/lab-orders/<pk>/status/ — lab_technician updates order status."""

    permission_classes = [IsAuthenticated, CanResultLabOrder]

    def patch(self, request, pk):

        order = get_object_or_404(LabOrder, pk=pk)
        if not can_access_patient(request.user, order.patient):
            log_action(
                request,
                action="ACCESS_DENIED",
                target=order.patient,
                patient=order.patient,
                is_cross_hospital=True,
            )
            return Response({"error": "Access denied."}, status=status.HTTP_403_FORBIDDEN)

        new_status = request.data.get("status")
        valid = [s[0] for s in LabOrder.Status.choices]
        if new_status not in valid:
            return Response(
                {"error": f"status must be one of {valid}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        order.status = new_status
        order.save(update_fields=["status"])
        log_action(
            request,
            action="UPDATE_LAB_ORDER",
            target=order,
            patient=order.patient,
            extra={"new_status": new_status},
        )
        return Response(LabOrderSerializer(order).data)


class LabOrderWorklistView(APIView):
    """
    GET /api/lab-orders/worklist/
    Lab-technician: all pending/in_progress orders for their hospital.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role not in (
            "lab_technician",
            "doctor",
            "nurse",
            "hospital_admin",
            "super_admin",
        ):
            return Response({"error": "Insufficient role."}, status=status.HTTP_403_FORBIDDEN)

        qs = LabOrder.objects.select_related("ordered_by", "patient").filter(
            status__in=["pending", "in_progress"]
        )
        if request.user.role not in ("super_admin",):
            qs = qs.filter(ordered_by__hospital=request.user.hospital)

        limit = min(int(request.query_params.get("limit", 200)), 500)
        return Response(
            LabOrderSerializer(qs.order_by("priority", "created_at")[:limit], many=True).data
        )
