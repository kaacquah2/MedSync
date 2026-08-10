"""
AI query endpoint — grounded clinical decision support.

POST /api/patients/<nhid>/ai-query/
Body: {"question": "What medications is this patient currently on?"}
Returns: {"answer": "...", "provider": "gemini", "model": "...", "context_size": 1234}

Guards:
  - IsAuthenticated
  - CanQueryAI (doctor, nurse, hospital_admin, super_admin)
  - can_access_patient (same gate as all patient endpoints)
  - log_action("AI_QUERY") — always audited
  - question length limit (max 500 chars) — prevents prompt injection abuse
"""

import logging

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from access.permissions import can_access_patient
from ai.models import AIQuery
from ai.service import query_patient
from api.permissions import CanQueryAI
from audit.utils import log_action
from patients.models import Patient
from records.models import VitalSign

logger = logging.getLogger(__name__)


class PatientAIQueryView(APIView):
    """POST /api/patients/<nhid>/ai-query/"""

    permission_classes = [IsAuthenticated, CanQueryAI]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "ai_query"

    def post(self, request, universal_id):
        patient = get_object_or_404(Patient, universal_id=universal_id)

        if not can_access_patient(request.user, patient):
            log_action(
                request,
                action="ACCESS_DENIED",
                target=patient,
                patient=patient,
                is_cross_hospital=True,
            )
            return Response({"error": "Access denied."}, status=status.HTTP_403_FORBIDDEN)

        question = str(request.data.get("question", "")).strip()
        if not question:
            return Response(
                {"error": "A question is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(question) > 500:
            return Response(
                {"error": "Question must be 500 characters or fewer."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Fetch authorised records for context
        encounters = list(
            patient.encounters.prefetch_related("diagnoses", "prescriptions", "lab_results")
            .select_related("created_at_hospital", "created_by")
            .order_by("-created_at")[:15]
        )
        vitals = list(VitalSign.objects.filter(patient=patient).order_by("-recorded_at")[:6])

        try:
            result = query_patient(
                patient=patient,
                encounters=encounters,
                records=None,  # encounters already prefetched with nested records
                vitals=vitals,
                question=question,
            )
        except RuntimeError as exc:
            return Response(
                {"error": str(exc), "configured": False},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except Exception:
            logger.exception("Unexpected AI query error for patient %s", universal_id)
            return Response(
                {"error": "AI service encountered an unexpected error. Please try again."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        import hashlib
        hashed_question = hashlib.sha256(question.encode("utf-8")).hexdigest()
        log_action(
            request,
            action="AI_QUERY",
            patient=patient,
            target=patient,
            extra={
                "question": question,
                "question_hash": hashed_question,
                "retrieved_records": result.get("retrieved_records", {}),
                "provider": result.get("provider"),
                "model": result.get("model"),
                "context_size": result.get("context_size"),
            },
        )

        try:
            AIQuery.objects.create(
                patient=patient,
                user=request.user,
                question=question,
                answer=result.get("answer", ""),
                provider=result.get("provider", ""),
                model=result.get("model", ""),
                context_size=result.get("context_size", 0),
            )
        except Exception:
            logger.exception("Failed to save AIQuery log entry for patient %s", universal_id)

        return Response(result)
