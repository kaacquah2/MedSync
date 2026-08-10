"""Hospital management API views."""

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from api.permissions import CanManageHospitals
from api.serializers import HospitalSerializer
from hospitals.models import Hospital


class HospitalListCreateView(APIView):
    """
    GET  /api/hospitals/    — list all hospitals (any authenticated user)
    POST /api/hospitals/    — create a hospital (SYSTEM_ADMIN only)
    """

    permission_classes = [IsAuthenticated, CanManageHospitals]

    def get(self, request):
        qs = Hospital.objects.all().order_by("name")

        is_active = request.GET.get("is_active")
        if is_active is not None:
            qs = qs.filter(is_active=(is_active.lower() == "true"))

        from rest_framework.pagination import PageNumberPagination

        paginator = PageNumberPagination()
        paginator.page_size = 50
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(
            HospitalSerializer(page, many=True, context={"request": request}).data
        )

    def post(self, request):
        # CanManageHospitals already enforces SYSTEM_ADMIN for write methods
        serializer = HospitalSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        hospital = serializer.save()
        return Response(
            HospitalSerializer(hospital, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class HospitalDetailView(APIView):
    """
    GET   /api/hospitals/<pk>/    — any authenticated user
    PATCH /api/hospitals/<pk>/    — SYSTEM_ADMIN only
    """

    permission_classes = [IsAuthenticated, CanManageHospitals]

    def get(self, request, pk):
        hospital = get_object_or_404(Hospital, pk=pk)
        return Response(HospitalSerializer(hospital, context={"request": request}).data)

    def patch(self, request, pk):
        hospital = get_object_or_404(Hospital, pk=pk)
        serializer = HospitalSerializer(hospital, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
