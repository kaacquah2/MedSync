"""
DRF serializers for the mEd REST API.

Encrypted fields (EncryptedCharField / EncryptedTextField) decrypt
transparently when accessed as Python attributes, so DRF serializers
work the same as regular Django model serializers.

PII-bearing serializers are ONLY returned through access-gated endpoints.
"""

from rest_framework import serializers

from accounts.models import User
from audit.models import AuditLog
from hospitals.models import Hospital
from patients.models import Patient, PatientAlert
from records.models import Diagnosis, Encounter, LabResult, MedicationAdministration, Prescription
from records.validators import validate_icd10, validate_loinc, validate_rxnorm, validate_snomed


# ── Shared helpers ─────────────────────────────────────────────────────────────


def _user_stub(user):
    if user:
        return {"id": user.pk, "full_name": user.get_full_name() or user.username}
    return None


def _is_cross_hospital(request, obj_hospital_id):
    if not request or not request.user.is_authenticated:
        return False
    user = request.user
    return (
        user.hospital is not None
        and obj_hospital_id is not None
        and user.hospital_id != obj_hospital_id
    )


def _mfa_enabled(user):
    from django_otp.plugins.otp_totp.models import TOTPDevice

    return TOTPDevice.objects.filter(user=user, confirmed=True).exists()


# ── Hospitals ─────────────────────────────────────────────────────────────────


class HospitalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Hospital
        fields = [
            "id",
            "name",
            "code",
            "address",
            "city",
            "country",
            "phone",
            "email",
            "website",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class HospitalMinimalSerializer(serializers.ModelSerializer):
    """Compact serializer for embedding hospital info in other resources."""

    class Meta:
        model = Hospital
        fields = ["id", "name", "code"]


# ── Users / Staff ─────────────────────────────────────────────────────────────


class MeSerializer(serializers.ModelSerializer):
    """Full profile serializer for the /api/me/ endpoint."""

    role_display = serializers.CharField(source="get_role_display", read_only=True)
    hospital = HospitalMinimalSerializer(read_only=True)
    full_name = serializers.CharField(source="get_full_name", read_only=True)
    is_clinical = serializers.BooleanField(read_only=True)
    is_admin_level = serializers.BooleanField(read_only=True)
    mfa_enabled = serializers.SerializerMethodField()
    recovery_codes_count = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "full_name",
            "email",
            "role",
            "role_display",
            "hospital",
            "is_clinical",
            "is_admin_level",
            "mfa_enabled",
            "recovery_codes_count",
            "phone",
            "bio",
            "date_joined",
        ]
        read_only_fields = fields

    def get_mfa_enabled(self, obj):
        return _mfa_enabled(obj)

    def get_recovery_codes_count(self, obj):
        return obj.recovery_codes.filter(used=False).count()


class StaffSerializer(serializers.ModelSerializer):
    """Staff member serializer for admin views."""

    role_display = serializers.CharField(source="get_role_display", read_only=True)
    hospital = HospitalMinimalSerializer(read_only=True)
    hospital_id = serializers.PrimaryKeyRelatedField(
        queryset=Hospital.objects.all(),
        source="hospital",
        write_only=True,
        allow_null=True,
        required=False,
    )
    full_name = serializers.CharField(source="get_full_name", read_only=True)
    is_clinical = serializers.BooleanField(read_only=True)
    mfa_enabled = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "full_name",
            "email",
            "password",
            "role",
            "role_display",
            "hospital",
            "hospital_id",
            "phone",
            "bio",
            "is_active",
            "is_clinical",
            "mfa_enabled",
            "date_joined",
        ]
        read_only_fields = ["id", "date_joined", "full_name", "is_clinical", "mfa_enabled"]
        extra_kwargs = {
            "password": {"write_only": True, "required": False},
        }

    def get_mfa_enabled(self, obj):
        return _mfa_enabled(obj)

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        user = User(**validated_data)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


# ── Patients ──────────────────────────────────────────────────────────────────


class PatientListSerializer(serializers.ModelSerializer):
    """
    Compact patient serializer for search results.
    Still decrypts name/dob — only returned to authenticated staff.
    """

    full_name = serializers.SerializerMethodField()
    registered_at_hospital = HospitalMinimalSerializer(read_only=True)

    class Meta:
        model = Patient
        fields = [
            "universal_id",
            "full_name",
            "first_name",
            "last_name",
            "date_of_birth",
            "sex",
            "blood_group",
            "registered_at_hospital",
            "created_at",
        ]

    def get_full_name(self, obj):
        try:
            return f"{obj.first_name} {obj.last_name}"
        except Exception:
            return ""


class PatientSerializer(serializers.ModelSerializer):
    """Full patient serializer with all PII — only via access-gated endpoints."""

    full_name = serializers.SerializerMethodField()
    registered_at_hospital = HospitalMinimalSerializer(read_only=True)
    registered_by = serializers.SerializerMethodField()
    sex_display = serializers.CharField(source="get_sex_display", read_only=True)
    blood_group_display = serializers.CharField(source="get_blood_group_display", read_only=True)
    active_alerts_count = serializers.SerializerMethodField()

    class Meta:
        model = Patient
        fields = [
            "universal_id",
            "full_name",
            "first_name",
            "last_name",
            "date_of_birth",
            "sex",
            "sex_display",
            "blood_group",
            "blood_group_display",
            "national_id",
            "phone",
            "email",
            "address",
            "registered_at_hospital",
            "registered_by",
            "active_alerts_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "universal_id",
            "created_at",
            "updated_at",
            "registered_at_hospital",
            "registered_by",
        ]

    def get_full_name(self, obj):
        try:
            return f"{obj.first_name} {obj.last_name}"
        except Exception:
            return ""

    def get_registered_by(self, obj):
        if obj.registered_by:
            return {
                "id": obj.registered_by.pk,
                "username": obj.registered_by.username,
                "full_name": obj.registered_by.get_full_name(),
            }
        return None

    def get_active_alerts_count(self, obj):
        val = getattr(obj, "active_alerts_count", None)
        if val is not None:
            return val
        return obj.alerts.filter(is_active=True).count()


class PatientAlertSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    severity_display = serializers.CharField(source="get_severity_display", read_only=True)
    recorded_by = serializers.SerializerMethodField()
    recorded_at_hospital = HospitalMinimalSerializer(read_only=True)
    is_high_risk = serializers.BooleanField(read_only=True)

    class Meta:
        model = PatientAlert
        fields = [
            "id",
            "kind",
            "kind_display",
            "label",
            "severity",
            "severity_display",
            "reaction",
            "recorded_by",
            "recorded_at_hospital",
            "is_active",
            "is_high_risk",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "recorded_by",
            "recorded_at_hospital",
            "is_high_risk",
        ]

    def get_recorded_by(self, obj):
        return _user_stub(obj.recorded_by)


# ── Clinical Records ───────────────────────────────────────────────────────────


class DiagnosisSerializer(serializers.ModelSerializer):
    created_by = serializers.SerializerMethodField()
    icd_code = serializers.CharField(
        required=False, allow_blank=True, validators=[validate_icd10]
    )
    snomed_code = serializers.CharField(
        required=False, allow_blank=True, validators=[validate_snomed]
    )

    class Meta:
        model = Diagnosis
        fields = [
            "id",
            "icd_code",
            "snomed_code",
            "description",
            "is_primary",
            "created_by",
            "created_at",
        ]
        read_only_fields = ["id", "created_by", "created_at"]

    def get_created_by(self, obj):
        return _user_stub(obj.created_by)


class PrescriptionSerializer(serializers.ModelSerializer):
    created_by = serializers.SerializerMethodField()
    rxnorm_code = serializers.CharField(
        required=False, allow_blank=True, validators=[validate_rxnorm]
    )

    class Meta:
        model = Prescription
        fields = [
            "id",
            "drug_name",
            "rxnorm_code",
            "dosage",
            "frequency",
            "instructions",
            "created_by",
            "created_at",
        ]
        read_only_fields = ["id", "created_by", "created_at"]

    def get_created_by(self, obj):
        return _user_stub(obj.created_by)


class LabResultSerializer(serializers.ModelSerializer):
    created_by = serializers.SerializerMethodField()
    patient_nhid = serializers.SerializerMethodField()
    loinc_code = serializers.CharField(
        required=False, allow_blank=True, validators=[validate_loinc]
    )

    class Meta:
        model = LabResult
        fields = [
            "id",
            "test_name",
            "loinc_code",
            "result_value",
            "reference_range",
            "is_abnormal",
            "performed_at",
            "created_by",
            "patient_nhid",
            "created_at",
        ]
        read_only_fields = ["id", "created_by", "patient_nhid", "created_at"]

    def get_created_by(self, obj):
        return _user_stub(obj.created_by)

    def get_patient_nhid(self, obj):
        try:
            return obj.encounter.patient.universal_id
        except Exception:
            return None


class EncounterSerializer(serializers.ModelSerializer):
    created_by = serializers.SerializerMethodField()
    created_at_hospital = HospitalMinimalSerializer(read_only=True)
    encounter_type_display = serializers.CharField(
        source="get_encounter_type_display", read_only=True
    )
    patient_nhid = serializers.CharField(source="patient.universal_id", read_only=True)
    patient_name = serializers.SerializerMethodField()
    diagnoses = DiagnosisSerializer(many=True, read_only=True)
    prescriptions = PrescriptionSerializer(many=True, read_only=True)
    lab_results = LabResultSerializer(many=True, read_only=True)
    is_cross_hospital = serializers.SerializerMethodField()

    class Meta:
        model = Encounter
        fields = [
            "id",
            "encounter_type",
            "encounter_type_display",
            "chief_complaint",
            "notes",
            "created_by",
            "created_at_hospital",
            "patient_nhid",
            "patient_name",
            "is_cross_hospital",
            "diagnoses",
            "prescriptions",
            "lab_results",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_by",
            "created_at_hospital",
            "patient_nhid",
            "patient_name",
            "is_cross_hospital",
            "diagnoses",
            "prescriptions",
            "lab_results",
            "created_at",
            "updated_at",
        ]

    def get_created_by(self, obj):
        if obj.created_by:
            return {
                "id": obj.created_by.pk,
                "full_name": obj.created_by.get_full_name() or obj.created_by.username,
                "role": obj.created_by.role,
            }
        return None

    def get_patient_name(self, obj):
        try:
            return f"{obj.patient.first_name} {obj.patient.last_name}"
        except Exception:
            return ""

    def get_is_cross_hospital(self, obj):
        return _is_cross_hospital(self.context.get("request"), obj.created_at_hospital_id)


class EncounterListSerializer(serializers.ModelSerializer):
    """Compact serializer for encounter lists (no nested records)."""

    created_by = serializers.SerializerMethodField()
    created_at_hospital = HospitalMinimalSerializer(read_only=True)
    encounter_type_display = serializers.CharField(
        source="get_encounter_type_display", read_only=True
    )
    patient_nhid = serializers.CharField(source="patient.universal_id", read_only=True)
    patient_name = serializers.SerializerMethodField()
    is_cross_hospital = serializers.SerializerMethodField()
    has_abnormal_labs = serializers.SerializerMethodField()

    class Meta:
        model = Encounter
        fields = [
            "id",
            "encounter_type",
            "encounter_type_display",
            "created_by",
            "created_at_hospital",
            "patient_nhid",
            "patient_name",
            "is_cross_hospital",
            "has_abnormal_labs",
            "created_at",
        ]

    def get_created_by(self, obj):
        return _user_stub(obj.created_by)

    def get_patient_name(self, obj):
        try:
            return f"{obj.patient.first_name} {obj.patient.last_name}"
        except Exception:
            return ""

    def get_is_cross_hospital(self, obj):
        return _is_cross_hospital(self.context.get("request"), obj.created_at_hospital_id)

    def get_has_abnormal_labs(self, obj):
        val = getattr(obj, "has_abnormal_labs", None)
        if val is not None:
            return val
        try:
            return obj.lab_results.filter(is_abnormal=True).exists()
        except Exception:
            return False


# ── Audit Log ─────────────────────────────────────────────────────────────────


class AuditLogSerializer(serializers.ModelSerializer):
    action_display = serializers.CharField(source="get_action_display", read_only=True)
    is_reviewed = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "actor_username",
            "actor_role",
            "actor_hospital",
            "action",
            "action_display",
            "timestamp",
            "target_type",
            "target_id",
            "patient_nhid",
            "is_cross_hospital",
            "ip_address",
            "extra",
            "is_reviewed",
        ]
        read_only_fields = fields

    def get_is_reviewed(self, obj):
        return hasattr(obj, "review")


# ── Dashboard helper serializers ───────────────────────────────────────────────


class RecentEncounterSerializer(serializers.ModelSerializer):
    patient_nhid = serializers.CharField(source="patient.universal_id", read_only=True)
    patient_name = serializers.SerializerMethodField()
    created_at_hospital = HospitalMinimalSerializer(read_only=True)
    encounter_type_display = serializers.CharField(
        source="get_encounter_type_display", read_only=True
    )
    is_cross_hospital = serializers.SerializerMethodField()
    has_abnormal_labs = serializers.SerializerMethodField()

    class Meta:
        model = Encounter
        fields = [
            "id",
            "encounter_type",
            "encounter_type_display",
            "patient_nhid",
            "patient_name",
            "created_at_hospital",
            "is_cross_hospital",
            "has_abnormal_labs",
            "created_at",
        ]

    def get_patient_name(self, obj):
        try:
            return f"{obj.patient.first_name} {obj.patient.last_name}"
        except Exception:
            return ""

    def get_is_cross_hospital(self, obj):
        return _is_cross_hospital(self.context.get("request"), obj.created_at_hospital_id)

    def get_has_abnormal_labs(self, obj):
        val = getattr(obj, "has_abnormal_labs", None)
        if val is not None:
            return val
        try:
            return obj.lab_results.filter(is_abnormal=True).exists()
        except Exception:
            return False


class RecentLabSerializer(serializers.ModelSerializer):
    patient_nhid = serializers.SerializerMethodField()
    patient_name = serializers.SerializerMethodField()

    class Meta:
        model = LabResult
        fields = [
            "id",
            "test_name",
            "is_abnormal",
            "patient_nhid",
            "patient_name",
            "created_at",
        ]

    def get_patient_nhid(self, obj):
        try:
            return obj.encounter.patient.universal_id
        except Exception:
            return None

    def get_patient_name(self, obj):
        try:
            p = obj.encounter.patient
            return f"{p.first_name} {p.last_name}"
        except Exception:
            return ""


class RecentAuditSerializer(serializers.ModelSerializer):
    action_display = serializers.CharField(source="get_action_display", read_only=True)

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "actor_username",
            "actor_role",
            "action",
            "action_display",
            "patient_nhid",
            "is_cross_hospital",
            "timestamp",
        ]


class MedicationAdministrationSerializer(serializers.ModelSerializer):
    prescription_drug_name = serializers.CharField(source="prescription.drug_name", read_only=True)
    prescription_dosage = serializers.CharField(source="prescription.dosage", read_only=True)
    prescription_frequency = serializers.CharField(source="prescription.frequency", read_only=True)
    patient_name = serializers.SerializerMethodField()
    patient_nhid = serializers.CharField(
        source="prescription.encounter.patient.universal_id", read_only=True
    )
    bed_label = serializers.SerializerMethodField()
    administered_by_name = serializers.CharField(
        source="administered_by.get_full_name", read_only=True, allow_null=True
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = MedicationAdministration
        fields = [
            "id",
            "prescription",
            "prescription_drug_name",
            "prescription_dosage",
            "prescription_frequency",
            "patient_name",
            "patient_nhid",
            "bed_label",
            "administered_by",
            "administered_by_name",
            "scheduled_time",
            "administered_time",
            "status",
            "status_display",
            "notes",
        ]
        read_only_fields = [
            "id",
            "prescription_drug_name",
            "prescription_dosage",
            "prescription_frequency",
            "patient_name",
            "patient_nhid",
            "bed_label",
            "administered_by_name",
            "status_display",
            "administered_time",
        ]

    def get_patient_name(self, obj):
        try:
            p = obj.prescription.encounter.patient
            return f"{p.first_name} {p.last_name}"
        except Exception:
            return ""

    def get_bed_label(self, obj):
        val = getattr(obj, "bed_label", None)
        if val is not None:
            return val
        try:
            p = obj.prescription.encounter.patient
            beds = list(p.current_bed.all())
            bed = beds[0] if beds else None
            if bed:
                return f"{bed.ward.name} · {bed.label}"
        except Exception:
            pass
        return "—"
