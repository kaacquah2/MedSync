"""Audit log API views — read-only list, action choices, and chain validation."""

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from api.permissions import CanViewAuditLog, IsSystemAdmin
from api.serializers import AuditLogSerializer
from audit.models import AuditLog, AuditLogReview
from audit.utils import log_action


class AuditLogListView(APIView):
    """
    GET /api/audit/?action=&nhid=&actor=&cross_hospital=true&page=n

    SYSTEM_ADMIN only. Returns paginated, filterable audit log entries.
    """

    permission_classes = [IsAuthenticated, CanViewAuditLog]

    def get(self, request):
        qs = AuditLog.objects.select_related("actor", "review").order_by("-timestamp")
        if request.user.role == "hospital_admin":
            hosp_str = str(request.user.hospital) if request.user.hospital else ""
            qs = qs.filter(actor_hospital=hosp_str)

        action = request.GET.get("action")
        nhid = request.GET.get("nhid")
        actor = request.GET.get("actor")
        cross_only = request.GET.get("cross_hospital", "").lower() in ("true", "1", "yes")
        date_from = request.GET.get("date_from")
        date_to = request.GET.get("date_to")

        if action:
            qs = qs.filter(action=action)
        if nhid:
            qs = qs.filter(patient_nhid__icontains=nhid)
        if actor:
            qs = qs.filter(actor_username__icontains=actor)
        if cross_only:
            qs = qs.filter(is_cross_hospital=True)
        if date_from:
            qs = qs.filter(timestamp__date__gte=date_from)
        if date_to:
            qs = qs.filter(timestamp__date__lte=date_to)

        from rest_framework.pagination import PageNumberPagination

        paginator = PageNumberPagination()
        paginator.page_size = 50
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(AuditLogSerializer(page, many=True).data)


class AuditActionChoicesView(APIView):
    """GET /api/audit/actions/ — returns all AuditLog.Action choices for filter dropdowns."""

    permission_classes = [IsAuthenticated, CanViewAuditLog]

    def get(self, request):
        choices = [{"value": value, "label": label} for value, label in AuditLog.Action.choices]
        return Response(choices)


class AuditChainValidateView(APIView):
    """
    POST /api/audit/validate-chain/
    Verifies the SHA-256 hash chain across all audit log rows.
    Returns per-node {id, valid, prev_hash, row_hash} for the chain visualiser.
    """

    permission_classes = [IsAuthenticated, CanViewAuditLog]

    def post(self, request):
        entries = AuditLog.objects.order_by("pk").only(
            "pk",
            "prev_hash",
            "row_hash",
            "actor_username",
            "actor_role",
            "actor_hospital",
            "action",
            "timestamp",
            "target_type",
            "target_id",
            "patient_nhid",
            "is_cross_hospital",
            "ip_address",
            "extra",
        )

        results = []
        prev_hash = None
        chain_valid = True
        count = 0

        for entry in entries.iterator(chunk_size=500):
            count += 1
            if prev_hash is None:
                prev_hash = entry.prev_hash

            fields = AuditLog._chain_fields_for(entry)
            expected_hash = AuditLog.compute_row_hash(entry.prev_hash, fields)

            row_valid = entry.row_hash == expected_hash and entry.prev_hash == prev_hash
            if not row_valid:
                chain_valid = False

            results.append(
                {
                    "id": entry.pk,
                    "valid": row_valid,
                    "prev_hash": entry.prev_hash[:12] + "…" if entry.prev_hash else "",
                    "row_hash": entry.row_hash[:12] + "…" if entry.row_hash else "",
                    "action": entry.action,
                    "actor": entry.actor_username,
                    "timestamp": str(entry.timestamp),
                }
            )

            prev_hash = entry.row_hash

        log_action(request, action="VALIDATE_AUDIT_CHAIN", extra={"chain_valid": chain_valid})
        return Response(
            {
                "chain_valid": chain_valid,
                "total_entries": count,
                "nodes": results,
            }
        )


class AuditLogReviewView(APIView):
    """
    POST /api/audit/<pk>/review/  — mark an audit log entry as reviewed
    DELETE /api/audit/<pk>/review/ — unmark an audit log entry as reviewed (undo)
    """

    permission_classes = [IsAuthenticated, IsSystemAdmin]

    def post(self, request, pk):
        audit_log = get_object_or_404(AuditLog, pk=pk)
        review, created = AuditLogReview.objects.get_or_create(
            audit_log=audit_log, defaults={"reviewed_by": request.user}
        )
        return Response({"status": "reviewed", "is_reviewed": True}, status=status.HTTP_200_OK)

    def delete(self, request, pk):
        audit_log = get_object_or_404(AuditLog, pk=pk)
        AuditLogReview.objects.filter(audit_log=audit_log).delete()
        return Response({"status": "pending", "is_reviewed": False}, status=status.HTTP_200_OK)
