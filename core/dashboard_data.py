"""
Per-role dashboard data builders for mEd.

Each build_<role>() function returns a dict with:
  stats              — list of {value, label, icon, color} for stat cards
  charts             — dict keyed by canvas-id → Chart.js config (JSON-safe)
  recent_encounters  — list of Encounter instances (where applicable)
  recent_audits      — list of AuditLog instances (SYSTEM_ADMIN only)
  recent_labs        — list of LabResult instances (LAB_TECH only)

IMPORTANT: Only non-encrypted columns are aggregated here
(created_at, encounter_type, is_abnormal, sex, registered_at_hospital,
FK ids, AuditLog.timestamp/is_cross_hospital/action).
Encrypted fields (first_name, last_name, etc.) are NEVER used in
.annotate()/.values()/.aggregate() — they are only accessed per-instance
at render time, which triggers transparent Fernet decryption.
"""

from datetime import date, timedelta

from django.db.models import Count
from django.db.models.functions import TruncDate

# ── Theme colours (match mEd Bootstrap vars) ───────────────────────────────
CHART_COLORS = {
    "blue": "#0d6efd",
    "green": "#198754",
    "teal": "#20c997",
    "red": "#dc3545",
    "amber": "#ffc107",
    "navy": "#1a2744",
    "purple": "#6f42c1",
    "cyan": "#0dcaf0",
    "palette": [
        "#0d6efd",
        "#198754",
        "#dc3545",
        "#ffc107",
        "#0dcaf0",
        "#6f42c1",
        "#fd7e14",
        "#1a2744",
    ],
}

_ENCOUNTER_TYPE_LABELS = {
    "OPD": "Outpatient",
    "IPD": "Inpatient",
    "EMRG": "Emergency",
    "FU": "Follow-up",
    "TM": "Telemedicine",
}

_SEX_LABELS = {"M": "Male", "F": "Female", "O": "Other"}


# ── Shared aggregation helpers ──────────────────────────────────────────────


def daily_series(qs, date_field="created_at", days=14):
    """
    Return (labels, counts) for the last *days* days, zero-filled.

    Uses TruncDate on *date_field* — safe because created_at / timestamp
    are never encrypted.  Returns plain Python int/str so the caller can
    dump to JSON via Django's json_script filter without extra serialization.
    """
    today = date.today()
    start = today - timedelta(days=days - 1)
    rows = (
        qs.filter(**{f"{date_field}__date__gte": start})
        .annotate(_day=TruncDate(date_field))
        .values("_day")
        .annotate(n=Count("id"))
        .order_by("_day")
    )
    counts = {row["_day"]: row["n"] for row in rows}
    labels, values = [], []
    for i in range(days):
        d = start + timedelta(days=i)
        labels.append(d.strftime("%d %b"))
        values.append(counts.get(d, 0))
    return labels, values


def category_counts(qs, field, label_map=None):
    """
    Return (labels, values) counts for a plain (non-encrypted) CharField.
    Applies *label_map* for human-readable display names if provided.
    """
    rows = qs.values(field).annotate(n=Count("id")).order_by("-n")
    labels = [label_map.get(r[field], r[field]) if label_map else (r[field] or "—") for r in rows]
    values = [r["n"] for r in rows]
    return labels, values


# ── Chart config factory helpers ────────────────────────────────────────────


def _line(label, labels, data, color_key="blue"):
    return {
        "type": "line",
        "labels": labels,
        "datasets": [{"label": label, "data": data, "color": CHART_COLORS[color_key]}],
    }


def _doughnut(labels, data):
    return {
        "type": "doughnut",
        "labels": labels,
        "datasets": [{"data": data, "colors": CHART_COLORS["palette"]}],
    }


def _bar(labels, data, color_key="blue"):
    color = CHART_COLORS[color_key]
    return {
        "type": "bar",
        "labels": labels,
        "datasets": [{"data": data, "colors": [color] * len(data)}],
    }


# ── Per-role builders ───────────────────────────────────────────────────────


def build_doctor(user):
    from django.db.models import Exists, OuterRef

    from patients.models import PatientAlert
    from records.models import Encounter, LabResult

    today = date.today()
    my_enc = Encounter.objects.filter(created_by=user)

    total = my_enc.count()
    today_count = my_enc.filter(created_at__date=today).count()
    patients_seen = my_enc.values("patient_id").distinct().count()
    active_alerts = (
        PatientAlert.objects.filter(recorded_at_hospital=user.hospital, is_active=True).count()
        if user.hospital
        else 0
    )

    labels, enc_values = daily_series(my_enc, "created_at")
    type_labels, type_values = category_counts(my_enc, "encounter_type", _ENCOUNTER_TYPE_LABELS)

    return {
        "stats": [
            {
                "value": total,
                "label": "My Encounters",
                "icon": "bi-journal-medical",
                "color": "primary",
                "link": "/worklist",
            },
            {
                "value": today_count,
                "label": "Today",
                "icon": "bi-calendar-day",
                "color": "info",
                "link": "/worklist",
            },
            {
                "value": patients_seen,
                "label": "Patients Seen",
                "icon": "bi-people",
                "color": "success",
                "link": "/patients",
            },
            {
                "value": active_alerts,
                "label": "Active Alerts (Hospital)",
                "icon": "bi-exclamation-triangle",
                "color": "danger",
                "link": "/alerts",
            },
        ],
        "recent_encounters": list(
            my_enc.select_related("patient")
            .annotate(
                has_abnormal_labs=Exists(
                    LabResult.objects.filter(encounter=OuterRef("pk"), is_abnormal=True)
                )
            )
            .order_by("-created_at")[:5]
        ),
        "charts": {
            "enc_trend": _line("My Encounters / Day", labels, enc_values),
            "enc_type": _doughnut(type_labels, type_values),
        },
    }


def build_nurse(user):
    """
    Nurse-specific dashboard — ward census, medications, and vitals.

    Deliberately different from build_doctor: nurses don't create encounters
    and don't need encounter statistics.  This builder surfaces the nursing
    metrics that matter at shift start: how many patients are on the ward,
    which medications are due, how many vitals sets were taken today, and
    whether any active alerts need attention.
    """
    from hospitals.models import Bed
    from patients.models import PatientAlert
    from records.models import MedicationAdministration, VitalSign

    today = date.today()

    # Occupied beds in this nurse's hospital — proxy for "patients on ward"
    occupied_beds = (
        Bed.objects.filter(ward__hospital=user.hospital, status="occupied").count()
        if user.hospital
        else 0
    )

    # Medications due across this hospital (via encounter → hospital chain)
    meds_due = (
        MedicationAdministration.objects.filter(
            prescription__encounter__created_at_hospital=user.hospital,
            status="due",
        ).count()
        if user.hospital
        else 0
    )

    # Vital signs recorded today by this nurse
    vitals_today = VitalSign.objects.filter(
        recorded_by=user,
        recorded_at__date=today,
    ).count()

    # Active clinical alerts at this hospital
    active_alerts = (
        PatientAlert.objects.filter(recorded_at_hospital=user.hospital, is_active=True).count()
        if user.hospital
        else 0
    )

    # Vitals trend (14 days) — by this nurse; uses recorded_at (not auto-now)
    my_vitals = VitalSign.objects.filter(recorded_by=user)
    labels, vitals_values = daily_series(my_vitals, "recorded_at")

    # Medication administration status breakdown for this hospital
    med_qs = (
        MedicationAdministration.objects.filter(
            prescription__encounter__created_at_hospital=user.hospital
        )
        if user.hospital
        else MedicationAdministration.objects.none()
    )
    status_labels, status_values = category_counts(
        med_qs,
        "status",
        {"due": "Due", "given": "Given", "held": "Held", "refused": "Refused", "missed": "Missed"},
    )

    return {
        "stats": [
            {
                "value": occupied_beds,
                "label": "Patients on Ward",
                "icon": "bi-people",
                "color": "primary",
                "link": "/patients",
            },
            {
                "value": meds_due,
                "label": "Medications Due",
                "icon": "bi-capsule",
                "color": "danger",
                "link": "/patients",
            },
            {
                "value": vitals_today,
                "label": "Vitals Recorded Today",
                "icon": "bi-heart-pulse",
                "color": "success",
                "link": "/patients",
            },
            {
                "value": active_alerts,
                "label": "Active Alerts",
                "icon": "bi-exclamation-triangle",
                "color": "warning",
                "link": "/alerts",
            },
        ],
        "charts": {
            "vitals_trend": _line("Vitals recorded / day", labels, vitals_values, "teal"),
            "med_status": _doughnut(status_labels, status_values),
        },
    }


def build_lab(user):
    from records.models import LabResult

    today = date.today()
    my_labs = LabResult.objects.filter(created_by=user)

    total = my_labs.count()
    today_count = my_labs.filter(created_at__date=today).count()
    abnormal_count = my_labs.filter(is_abnormal=True).count()
    normal_count = total - abnormal_count
    abnormal_rate = round(abnormal_count / total * 100) if total else 0

    labels, lab_values = daily_series(my_labs, "created_at")

    return {
        "stats": [
            {
                "value": total,
                "label": "Labs Entered",
                "icon": "bi-flask",
                "color": "primary",
                "link": "/lab/results",
            },
            {
                "value": today_count,
                "label": "Today",
                "icon": "bi-calendar-day",
                "color": "info",
                "link": "/lab/results",
            },
            {
                "value": abnormal_count,
                "label": "Abnormal Results",
                "icon": "bi-exclamation-circle",
                "color": "danger",
                "link": "/lab/results",
            },
            {
                "value": f"{abnormal_rate}%",
                "label": "Abnormal Rate",
                "icon": "bi-graph-up",
                "color": "warning",
            },
        ],
        "recent_labs": list(
            my_labs.select_related("encounter__patient").order_by("-created_at")[:5]
        ),
        "charts": {
            "lab_trend": _line("Labs Entered / Day", labels, lab_values, "teal"),
            "lab_abnormal": _doughnut(["Normal", "Abnormal"], [normal_count, abnormal_count]),
        },
    }


def build_receptionist(user):
    from patients.models import Patient
    from scheduling.models import Appointment

    today = date.today()

    hosp_qs = (
        Patient.objects.filter(registered_at_hospital=user.hospital)
        if user.hospital
        else Patient.objects.none()
    )
    total_hosp = hosp_qs.count()

    # Today's appointment activity for this hospital
    today_appts = (
        Appointment.objects.filter(
            hospital=user.hospital,
            scheduled_for__date=today,
        )
        if user.hospital
        else Appointment.objects.none()
    )
    total_appts_today = today_appts.count()
    checked_in = today_appts.filter(status__in=["checked_in", "in_progress", "completed"]).count()
    no_shows = today_appts.filter(status="no_show").count()

    # Registration trend (14 days) + appointment type breakdown
    labels, reg_values = daily_series(hosp_qs, "created_at")
    appt_type_labels, appt_type_values = category_counts(
        today_appts,
        "appointment_type",
        {
            "outpatient": "Outpatient",
            "follow_up": "Follow-up",
            "procedure": "Procedure",
            "lab": "Lab",
            "emergency": "Emergency",
        },
    )

    return {
        "stats": [
            {
                "value": total_hosp,
                "label": "Hospital Patients",
                "icon": "bi-people",
                "color": "primary",
                "link": "/patients",
            },
            {
                "value": total_appts_today,
                "label": "Appointments Today",
                "icon": "bi-calendar-day",
                "color": "info",
                "link": "/appointments",
            },
            {
                "value": checked_in,
                "label": "Checked In",
                "icon": "bi-people",
                "color": "success",
                "link": "/appointments",
            },
            {
                "value": no_shows,
                "label": "No-Shows",
                "icon": "bi-exclamation-circle",
                "color": "danger",
                "link": "/appointments",
            },
        ],
        "charts": {
            "reg_trend": _line("Patient registrations / day", labels, reg_values, "green"),
            "appt_status": _doughnut(appt_type_labels, appt_type_values),
        },
    }


def build_hospital_admin(user):
    from accounts.models import User as StaffUser
    from patients.models import Patient
    from records.models import Encounter

    today = date.today()

    hosp_enc = (
        Encounter.objects.filter(created_at_hospital=user.hospital)
        if user.hospital
        else Encounter.objects.none()
    )
    hosp_pts = (
        Patient.objects.filter(registered_at_hospital=user.hospital)
        if user.hospital
        else Patient.objects.none()
    )
    active_staff = (
        StaffUser.objects.filter(hospital=user.hospital, is_active=True).count()
        if user.hospital
        else 0
    )

    total_patients = hosp_pts.count()
    total_enc = hosp_enc.count()
    today_enc = hosp_enc.filter(created_at__date=today).count()

    labels, enc_values = daily_series(hosp_enc, "created_at")
    type_labels, type_values = category_counts(hosp_enc, "encounter_type", _ENCOUNTER_TYPE_LABELS)

    return {
        "stats": [
            {
                "value": total_patients,
                "label": "Hospital Patients",
                "icon": "bi-people",
                "color": "primary",
                "link": "/patients",
            },
            {
                "value": total_enc,
                "label": "Hospital Encounters",
                "icon": "bi-journal-medical",
                "color": "info",
                "link": "/patients",
            },
            {
                "value": active_staff,
                "label": "Active Staff",
                "icon": "bi-person-badge",
                "color": "success",
                "link": "/staff",
            },
            {
                "value": today_enc,
                "label": "Encounters Today",
                "icon": "bi-calendar-day",
                "color": "warning",
                "link": "/patients",
            },
        ],
        "recent_encounters": list(
            hosp_enc.select_related("patient", "created_by").order_by("-created_at")[:5]
        ),
        "charts": {
            "enc_trend": _line("Encounters / Day", labels, enc_values),
            "enc_type": _bar(type_labels, type_values),
        },
    }


def build_system_admin(user):
    from audit.models import AuditLog
    from hospitals.models import Hospital
    from patients.models import Patient
    from records.models import Encounter

    today = date.today()
    thirty_days_ago = today - timedelta(days=30)

    total_hospitals = Hospital.objects.count()
    total_patients = Patient.objects.count()
    total_encounters = Encounter.objects.count()
    cross_30d = AuditLog.objects.filter(
        is_cross_hospital=True,
        timestamp__date__gte=thirty_days_ago,
    ).count()

    all_enc = Encounter.objects.all()
    labels, enc_values = daily_series(all_enc, "created_at")

    cross_qs = AuditLog.objects.filter(is_cross_hospital=True)
    _, cross_values = daily_series(cross_qs, "timestamp")

    # Top hospitals by encounter count (skip null hospital names)
    hosp_rows = (
        Encounter.objects.values("created_at_hospital__name")
        .annotate(n=Count("id"))
        .order_by("-n")[:6]
    )
    hosp_labels = [r["created_at_hospital__name"] or "Unknown" for r in hosp_rows]
    hosp_values = [r["n"] for r in hosp_rows]

    return {
        "stats": [
            {
                "value": total_hospitals,
                "label": "Hospitals",
                "icon": "bi-building",
                "color": "primary",
                "link": "/superadmin/hospitals",
            },
            {
                "value": total_patients,
                "label": "Patients",
                "icon": "bi-people",
                "color": "success",
                "link": "/patients",
            },
            {
                "value": total_encounters,
                "label": "Encounters",
                "icon": "bi-journal-medical",
                "color": "info",
                "link": "/patients",
            },
            {
                "value": cross_30d,
                "label": "Cross-Hospital (30 days)",
                "icon": "bi-arrow-left-right",
                "color": "danger",
                "link": "/superadmin/audit-logs",
            },
        ],
        "recent_audits": list(AuditLog.objects.select_related("actor").order_by("-timestamp")[:10]),
        "charts": {
            "enc_trend": _line("Encounters / Day", labels, enc_values),
            "cross_trend": _line("Cross-Hospital Events / Day", labels, cross_values, "red"),
            "hosp_dist": _doughnut(hosp_labels, hosp_values),
        },
    }
