"""
Dashboard API — returns role-specific stats, charts and recent items.

Delegates entirely to the existing core.dashboard_data.build_<role>() functions
so the dashboard logic stays in one place.
"""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

import core.dashboard_data as dd
from api.serializers import (
    RecentAuditSerializer,
    RecentEncounterSerializer,
    RecentLabSerializer,
)

_BUILDERS = {
    "doctor": dd.build_doctor,
    "nurse": dd.build_nurse,
    "lab_technician": dd.build_lab,
    "receptionist": dd.build_receptionist,
    "hospital_admin": dd.build_hospital_admin,
    "super_admin": dd.build_system_admin,
}


class DashboardView(APIView):
    """GET /api/dashboard/ — role-branched dashboard payload."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        if getattr(request.user, "is_superuser", False):
            role = "super_admin"
            builder = dd.build_system_admin
        else:
            role = request.user.role
            builder = _BUILDERS.get(role, dd.build_system_admin)

        raw = builder(request.user)

        ctx = {"request": request}

        result = {
            "role": role,
            "stats": raw.get("stats", []),
            "charts": raw.get("charts", {}),
        }

        if "recent_encounters" in raw:
            result["recent_encounters"] = RecentEncounterSerializer(
                raw["recent_encounters"], many=True, context=ctx
            ).data

        if "recent_audits" in raw:
            result["recent_audits"] = RecentAuditSerializer(
                raw["recent_audits"], many=True, context=ctx
            ).data

        if "recent_labs" in raw:
            result["recent_labs"] = RecentLabSerializer(
                raw["recent_labs"], many=True, context=ctx
            ).data

        return Response(result)
