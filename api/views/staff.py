"""
Staff management API views.

HOSPITAL_ADMIN: manage staff at own hospital only (scoped by hospital FK).
SYSTEM_ADMIN  : manage any staff at any hospital.
"""

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from api.permissions import CanManageStaff
from api.serializers import StaffSerializer
from audit.utils import log_action


class StaffListCreateView(APIView):
    """
    GET  /api/staff/   — list staff (HOSPITAL_ADMIN: own hospital; SYSTEM_ADMIN: all)
    POST /api/staff/   — create a new staff member
    """

    permission_classes = [IsAuthenticated, CanManageStaff]

    def get(self, request):
        qs = User.objects.select_related("hospital").order_by("last_name", "first_name")

        if request.user.role == "hospital_admin":
            qs = qs.filter(hospital=request.user.hospital)

        # Optional filters
        role = request.GET.get("role")
        is_active = request.GET.get("is_active")
        hospital_id = request.GET.get("hospital_id")
        q = request.GET.get("q") or request.GET.get("username")

        if role:
            qs = qs.filter(role=role)
        if is_active is not None:
            qs = qs.filter(is_active=(is_active.lower() == "true"))
        if hospital_id and (request.user.role == "super_admin" or getattr(request.user, "is_superuser", False)):
            qs = qs.filter(hospital_id=hospital_id)
        if q:
            from django.db.models import Q
            qs = qs.filter(
                Q(username__icontains=q)
                | Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
                | Q(email__icontains=q)
            )

        from rest_framework.pagination import PageNumberPagination

        paginator = PageNumberPagination()
        paginator.page_size = 30
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(
            StaffSerializer(page, many=True, context={"request": request}).data
        )

    def post(self, request):
        data = request.data.copy()

        # hospital_admin cannot create super_admin
        if request.user.role == "hospital_admin":
            if data.get("role") == "super_admin":
                return Response(
                    {"error": "hospital_admin cannot assign the super_admin role."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            if not request.user.hospital_id:
                return Response(
                    {"error": "Hospital administrator account is not assigned to a hospital."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            # Force hospital to be the admin's own hospital
            data["hospital_id"] = request.user.hospital_id

        serializer = StaffSerializer(data=data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        # Validate the initial password through configured validators
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError as DjangoValidationError

        password = request.data.get("password")
        if not password:
            return Response(
                {"error": "Initial password is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            from accounts.models import User
            user_attrs = {
                k: v for k, v in serializer.validated_data.items()
                if k not in ("hospital_id", "hospital", "password")
            }
            if serializer.validated_data.get("hospital"):
                user_attrs["hospital"] = serializer.validated_data["hospital"]
            temp_user = User(**user_attrs)
            validate_password(password, user=temp_user)
        except DjangoValidationError as exc:
            return Response(
                {"error": " ".join(exc.messages)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = serializer.save()

        return Response(
            StaffSerializer(user, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class StaffDetailView(APIView):
    """
    GET   /api/staff/<pk>/
    PATCH /api/staff/<pk>/
    """

    permission_classes = [IsAuthenticated, CanManageStaff]

    def _get_or_403(self, request, pk):
        user = get_object_or_404(User.objects.select_related("hospital"), pk=pk)
        if request.user.role == "hospital_admin" and user.hospital != request.user.hospital:
            return None
        return user

    def get(self, request, pk):
        user = self._get_or_403(request, pk)
        if not user:
            return Response({"error": "Access denied."}, status=status.HTTP_403_FORBIDDEN)
        return Response(StaffSerializer(user, context={"request": request}).data)

    def patch(self, request, pk):
        user = self._get_or_403(request, pk)
        if not user:
            return Response({"error": "Access denied."}, status=status.HTTP_403_FORBIDDEN)

        data = request.data.copy()
        if request.user.role == "hospital_admin":
            if data.get("role") == "super_admin":
                return Response(
                    {"error": "hospital_admin cannot assign the super_admin role."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            data.pop("hospital_id", None)
            data.pop("hospital", None)

        serializer = StaffSerializer(
            user, data=data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(StaffSerializer(user, context={"request": request}).data)


class StaffSetActiveView(APIView):
    """POST /api/staff/<pk>/set-active/ — { "is_active": true|false }"""

    permission_classes = [IsAuthenticated, CanManageStaff]

    def post(self, request, pk):
        user = get_object_or_404(User.objects.select_related("hospital"), pk=pk)

        if request.user.role == "hospital_admin" and user.hospital != request.user.hospital:
            return Response({"error": "Access denied."}, status=status.HTTP_403_FORBIDDEN)

        # Can't deactivate yourself
        if user.pk == request.user.pk:
            return Response(
                {"error": "You cannot deactivate your own account."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        is_active = request.data.get("is_active")
        if is_active is None:
            return Response(
                {"error": "'is_active' field is required."}, status=status.HTTP_400_BAD_REQUEST
            )

        user.is_active = bool(is_active)
        user.save(update_fields=["is_active"])

        action = "STAFF_ACTIVATED" if user.is_active else "STAFF_DEACTIVATED"
        log_action(request, action=action, extra={"target_user": user.username})

        return Response(
            {
                "detail": f"Staff member {'activated' if user.is_active else 'deactivated'}.",
                "is_active": user.is_active,
            }
        )


class StaffResetPasswordView(APIView):
    """
    POST /api/staff/<pk>/reset-password/ — { "password": "<new_temp_password>" }

    Allows a HOSPITAL_ADMIN (own hospital only) or SYSTEM_ADMIN to set a new
    temporary password for a staff member.  The target user must log in and
    change it themselves via Profile → Security.
    """

    permission_classes = [IsAuthenticated, CanManageStaff]

    def post(self, request, pk):
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError as DjangoValidationError

        target = get_object_or_404(User.objects.select_related("hospital"), pk=pk)

        # hospital_admin may only reset passwords for staff at their own hospital
        if request.user.role == "hospital_admin" and target.hospital != request.user.hospital:
            return Response({"error": "Access denied."}, status=status.HTTP_403_FORBIDDEN)

        # Prevent resetting your own password via this admin endpoint
        # (use /api/auth/password/change/ instead)
        if target.pk == request.user.pk:
            return Response(
                {"error": "Use /api/auth/password/change/ to change your own password."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        password = request.data.get("password")
        if not password:
            return Response(
                {"error": "New password is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            validate_password(password, user=target)
        except DjangoValidationError as exc:
            return Response(
                {"error": " ".join(exc.messages)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        target.set_password(password)
        target.save(update_fields=["password"])

        log_action(
            request,
            action="RESET_STAFF_PASSWORD",
            target=target,
            extra={"target_user": target.username},
        )

        return Response(
            {"detail": f"Password for {target.username} has been reset."},
            status=status.HTTP_200_OK,
        )
