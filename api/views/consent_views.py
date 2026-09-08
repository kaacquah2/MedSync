"""PatientConsent API — patient data sharing consent management."""

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from access.models import PatientConsent
from api.permissions import IsAdminOrClinical
from audit.utils import log_action
from hospitals.models import Hospital
from patients.models import Patient


class PatientConsentSerializer(serializers.ModelSerializer):
    patient_nhid = serializers.CharField(source="patient.universal_id", read_only=True)
    patient_name = serializers.SerializerMethodField()
    hospital_name = serializers.CharField(source="hospital.name", read_only=True)

    class Meta:
        model = PatientConsent
        fields = [
            "id",
            "patient",
            "patient_nhid",
            "patient_name",
            "hospital",
            "hospital_name",
            "granted",
            "granted_at",
            "revoked_at",
            "notes",
        ]
        read_only_fields = ["id", "patient_nhid", "patient_name", "hospital_name", "granted_at"]

    def get_patient_name(self, obj):
        try:
            return f"{obj.patient.first_name} {obj.patient.last_name}"
        except Exception:
            return ""


class PatientConsentListCreateView(APIView):
    """
    GET  /api/consents/   — list consents for patient or hospital
    POST /api/consents/   — grant consent for a patient to a hospital
    """

    permission_classes = [IsAuthenticated, IsAdminOrClinical]

    def get(self, request):
        qs = PatientConsent.objects.select_related("patient", "hospital")
        patient_nhid = request.GET.get("patient") or request.GET.get("patient_nhid")
        if patient_nhid:
            if isinstance(patient_nhid, str) and patient_nhid.startswith("NHID"):
                qs = qs.filter(patient__universal_id=patient_nhid)
            else:
                qs = qs.filter(patient_id=patient_nhid)

        hospital_id = request.GET.get("hospital")
        if hospital_id:
            qs = qs.filter(hospital_id=hospital_id)
        elif request.user.role != "super_admin" and getattr(request.user, "hospital", None):
            qs = qs.filter(hospital=request.user.hospital)

        data = PatientConsentSerializer(qs, many=True).data
        log_action(
            request,
            action="VIEW_CONSENTS",
            target=getattr(request.user, "hospital", None),
            extra={"count": len(data)},
        )
        return Response(data)

    def post(self, request):
        patient_id = request.data.get("patient") or request.data.get("patient_nhid")
        hospital_id = request.data.get("hospital")

        patient = (
            get_object_or_404(Patient, universal_id=patient_id)
            if isinstance(patient_id, str) and patient_id.startswith("NHID")
            else get_object_or_404(Patient, pk=patient_id)
        )
        hospital = get_object_or_404(Hospital, pk=hospital_id)

        consent, created = PatientConsent.objects.get_or_create(
            patient=patient,
            hospital=hospital,
            defaults={
                "granted": True,
                "granted_at": timezone.now(),
                "notes": request.data.get("notes", ""),
            },
        )
        if not created:
            consent.granted = True
            consent.revoked_at = None
            if "notes" in request.data:
                consent.notes = request.data["notes"]
            consent.save()

        log_action(
            request,
            action="GRANT_CONSENT",
            target=consent,
            patient=patient,
            extra={"hospital_code": hospital.code},
        )
        return Response(PatientConsentSerializer(consent).data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class PatientConsentDetailView(APIView):
    """
    GET    /api/consents/<pk>/ — view consent detail
    PATCH  /api/consents/<pk>/ — revoke or update consent
    DELETE /api/consents/<pk>/ — revoke consent
    """

    permission_classes = [IsAuthenticated, IsAdminOrClinical]

    def get(self, request, pk):
        consent = get_object_or_404(PatientConsent, pk=pk)
        return Response(PatientConsentSerializer(consent).data)

    def patch(self, request, pk):
        consent = get_object_or_404(PatientConsent, pk=pk)
        granted = request.data.get("granted")
        if granted is False:
            consent.granted = False
            consent.revoked_at = timezone.now()
        elif granted is True:
            consent.granted = True
            consent.revoked_at = None

        if "notes" in request.data:
            consent.notes = request.data["notes"]

        consent.save()
        log_action(
            request,
            action="REVOKE_CONSENT" if not consent.granted else "GRANT_CONSENT",
            target=consent,
            patient=consent.patient,
            extra={"hospital_code": consent.hospital.code},
        )
        return Response(PatientConsentSerializer(consent).data)

    def delete(self, request, pk):
        consent = get_object_or_404(PatientConsent, pk=pk)
        consent.granted = False
        consent.revoked_at = timezone.now()
        consent.save()
        log_action(
            request,
            action="REVOKE_CONSENT",
            target=consent,
            patient=consent.patient,
            extra={"hospital_code": consent.hospital.code},
        )
        return Response({"status": "Consent revoked"}, status=status.HTTP_200_OK)
