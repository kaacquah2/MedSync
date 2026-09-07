"""Patient document upload, list, download and delete API."""

import io
import logging
import os
import zipfile

from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils.text import slugify
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from access.permissions import can_access_patient
from api.permissions import IsAdminOrClinical
from audit.utils import log_action
from patients.models import Patient
from records.models import PatientDocument

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB

ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".txt", ".docx"}
ALLOWED_MIMES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "text/plain",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

EXTENSION_TO_MIME = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".txt": "text/plain",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def sanitize_filename(filename: str) -> str:
    """Sanitize filename to prevent path traversal and header injection."""
    base, ext = os.path.splitext(filename)
    clean_base = slugify(base)
    if not clean_base:
        clean_base = "document"
    ext = ext.lower()
    if ext not in ALLOWED_EXTENSIONS:
        ext = ".bin"
    return f"{clean_base}{ext}"


def sniff_file_mime(first_bytes: bytes, file_obj=None) -> str | None:
    """Sniff magic bytes and structural signatures to verify file type against the allowlist."""
    if first_bytes.startswith(b"%PDF-"):
        return "application/pdf"
    elif first_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    elif first_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    elif first_bytes.startswith(b"PK\x03\x04"):
        # Validate that this is actually a DOCX container, not an arbitrary zip archive
        is_docx = False
        if file_obj is not None:
            try:
                cur_pos = file_obj.tell() if hasattr(file_obj, "tell") else 0
                file_obj.seek(0)
                with zipfile.ZipFile(file_obj) as zf:
                    names = zf.namelist()
                    if "[Content_Types].xml" in names or any(n.startswith("word/") for n in names):
                        is_docx = True
            except Exception:
                is_docx = False
            finally:
                if hasattr(file_obj, "seek"):
                    file_obj.seek(cur_pos)
        else:
            try:
                with zipfile.ZipFile(io.BytesIO(first_bytes)) as zf:
                    names = zf.namelist()
                    if "[Content_Types].xml" in names or any(n.startswith("word/") for n in names):
                        is_docx = True
            except Exception:
                if b"[Content_Types].xml" in first_bytes or b"word/" in first_bytes:
                    is_docx = True

        if is_docx:
            return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        return None

    # Text check: disallow null bytes, decode with errors="ignore", and check for binary control characters
    if b"\x00" not in first_bytes:
        try:
            text = first_bytes.decode("utf-8", errors="ignore")
            if text.strip():
                # Disallow control characters other than standard whitespace (\t, \n, \r)
                control_chars = sum(
                    1 for ch in text if ord(ch) < 32 and ch not in ("\t", "\n", "\r")
                )
                if control_chars == 0:
                    return "text/plain"
        except Exception:
            pass
    return None


class PatientDocumentSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.SerializerMethodField()
    download_url = serializers.SerializerMethodField()
    file_size_kb = serializers.SerializerMethodField()

    class Meta:
        model = PatientDocument
        fields = [
            "id",
            "original_name",
            "file_type",
            "file_size",
            "file_size_kb",
            "description",
            "uploaded_by",
            "uploaded_by_name",
            "download_url",
            "created_at",
        ]
        read_only_fields = fields

    def get_uploaded_by_name(self, obj):
        if obj.uploaded_by:
            return obj.uploaded_by.get_full_name() or obj.uploaded_by.username
        return None

    def get_download_url(self, obj):
        request = self.context.get("request")
        if obj.file and request:
            return request.build_absolute_uri(
                f"/api/patients/{obj.patient.universal_id}/documents/{obj.pk}/download/"
            )
        return None

    def get_file_size_kb(self, obj):
        if obj.file_size:
            return round(obj.file_size / 1024, 1)
        return 0


class PatientDocumentListUploadView(APIView):
    """
    GET  /api/patients/<nhid>/documents/  — list documents
    POST /api/patients/<nhid>/documents/  — upload (multipart/form-data, field: "file")
    """

    permission_classes = [IsAuthenticated, IsAdminOrClinical]
    throttle_scope = "document_upload"

    def get_throttles(self):
        if self.request.method == "POST":
            return [ScopedRateThrottle()]
        return []

    def _patient_or_403(self, request, nhid):
        patient = get_object_or_404(Patient, universal_id=nhid)
        if not can_access_patient(request.user, patient).allowed:
            return None, patient
        return patient, None

    def get(self, request, nhid):
        patient, target_p = self._patient_or_403(request, nhid)
        if patient is None:
            log_action(
                request,
                action="ACCESS_DENIED",
                target=target_p,
                patient=target_p,
                is_cross_hospital=True,
            )
            return Response({"error": "Access denied."}, status=status.HTTP_403_FORBIDDEN)

        from rest_framework.pagination import PageNumberPagination

        docs = (
            PatientDocument.objects.filter(patient=patient)
            .select_related("uploaded_by")
            .order_by("-created_at")
        )
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(docs, request)
        serializer = PatientDocumentSerializer(page, many=True, context={"request": request})
        log_action(request, action="LIST_DOCUMENTS", target=patient, patient=patient)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request, nhid):
        # Override throttle scope just for POST upload
        self.throttle_scope = "document_upload"

        patient, target_p = self._patient_or_403(request, nhid)
        if patient is None:
            log_action(
                request,
                action="ACCESS_DENIED",
                target=target_p,
                patient=target_p,
                is_cross_hospital=True,
            )
            return Response({"error": "Access denied."}, status=status.HTTP_403_FORBIDDEN)

        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            return Response({"error": "No file provided."}, status=status.HTTP_400_BAD_REQUEST)

        if uploaded_file.size > MAX_UPLOAD_BYTES:
            return Response(
                {
                    "error": f"File too large. Maximum size is {MAX_UPLOAD_BYTES // (1024 * 1024)} MB."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 1. Extension Allowlist
        ext = os.path.splitext(uploaded_file.name)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            return Response(
                {
                    "error": f"File extension '{ext}' is not allowed. Allowed: {list(ALLOWED_EXTENSIONS)}"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 2. Magic-byte Sniffing
        first_bytes = uploaded_file.read(512)
        uploaded_file.seek(0)
        sniffed_mime = sniff_file_mime(first_bytes, file_obj=uploaded_file)
        expected_mime = EXTENSION_TO_MIME.get(ext)
        if not sniffed_mime or sniffed_mime != expected_mime:
            return Response(
                {"error": "Invalid file content type or signature mismatch."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 3. Filename Sanitization
        safe_name = sanitize_filename(uploaded_file.name)

        # 4. Encrypt raw bytes at rest
        from django.core.files.base import ContentFile

        from core.fields import encrypt_bytes

        raw_bytes = uploaded_file.read()
        encrypted_bytes = encrypt_bytes(raw_bytes)
        encrypted_file = ContentFile(encrypted_bytes, name=safe_name)

        doc = PatientDocument.objects.create(
            patient=patient,
            uploaded_by=request.user,
            file=encrypted_file,
            original_name=safe_name,
            file_type=sniffed_mime,
            file_size=len(raw_bytes),  # original unencrypted file size
            description=(request.data.get("description") or "")[:255],
        )
        log_action(
            request,
            action="UPLOAD_DOCUMENT",
            target=patient,
            patient=patient,
            extra={
                "document_id": doc.pk,
                "file_size": doc.file_size,
            },
        )
        serializer = PatientDocumentSerializer(doc, context={"request": request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class PatientDocumentDownloadView(APIView):
    """GET /api/patients/<nhid>/documents/<pk>/download/ — serve file with auth."""

    permission_classes = [IsAuthenticated, IsAdminOrClinical]

    def get(self, request, nhid, pk):
        patient = get_object_or_404(Patient, universal_id=nhid)
        if not can_access_patient(request.user, patient).allowed:
            log_action(
                request,
                action="ACCESS_DENIED",
                target=patient,
                patient=patient,
                is_cross_hospital=True,
            )
            return Response({"error": "Access denied."}, status=status.HTTP_403_FORBIDDEN)

        doc = get_object_or_404(PatientDocument, pk=pk, patient=patient)

        if not doc.file:
            raise Http404("No file attached to this document record.")

        try:
            encrypted_bytes = doc.file.read()
        except FileNotFoundError:
            raise Http404("File not found on server.") from None

        # Decrypt if encrypted, otherwise serve plaintext fallback (for backwards compatibility)
        from core.fields import decrypt_bytes

        if encrypted_bytes.startswith(b"gAAAAA"):
            try:
                decrypted_bytes = decrypt_bytes(encrypted_bytes)
            except Exception as exc:
                logger.exception(
                    "Failed to decrypt document %s for patient %s: %s",
                    doc.pk,
                    patient.universal_id,
                    exc,
                )
                return Response(
                    {"error": "Failed to decrypt document. Please contact an administrator."},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
        else:
            decrypted_bytes = encrypted_bytes

        log_action(
            request,
            action="DOWNLOAD_DOCUMENT",
            target=patient,
            patient=patient,
            extra={"document_id": doc.pk},
        )
        response = FileResponse(
            io.BytesIO(decrypted_bytes), content_type=doc.file_type or "application/octet-stream"
        )
        safe_name = sanitize_filename(doc.original_name)
        response["Content-Disposition"] = f'attachment; filename="{safe_name}"'
        return response


class PatientDocumentDeleteView(APIView):
    """DELETE /api/patients/<nhid>/documents/<pk>/ — delete document and file."""

    permission_classes = [IsAuthenticated, IsAdminOrClinical]

    def delete(self, request, nhid, pk):
        patient = get_object_or_404(Patient, universal_id=nhid)
        if not can_access_patient(request.user, patient).allowed:
            log_action(
                request,
                action="ACCESS_DENIED",
                target=patient,
                patient=patient,
                is_cross_hospital=True,
            )
            return Response({"error": "Access denied."}, status=status.HTTP_403_FORBIDDEN)

        doc = get_object_or_404(PatientDocument, pk=pk, patient=patient)
        doc_id = doc.pk
        from django.db import transaction

        with transaction.atomic():
            if doc.file:
                doc.file.delete(save=False)
            doc.delete()

        log_action(
            request,
            action="DELETE_DOCUMENT",
            target=patient,
            patient=patient,
            extra={"document_id": doc_id},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
