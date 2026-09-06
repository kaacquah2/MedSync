"""
DRF permission classes mirroring the backend's role-based checks.

These are used on every API view so the API enforces the same RBAC rules.
"""

from rest_framework.permissions import BasePermission
from rest_framework.throttling import ScopedRateThrottle  # noqa: F401 — re-exported for views


def _has_role(user, *roles):
    return getattr(user, "role", None) in roles


class IsSystemAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and (
            _has_role(request.user, "super_admin") or getattr(request.user, "is_superuser", False)
        )


class IsHospitalAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and _has_role(
            request.user, "hospital_admin", "super_admin"
        )


class IsDoctor(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and _has_role(request.user, "doctor")


class IsDoctorOrNurse(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and _has_role(request.user, "doctor", "nurse")


class IsClinical(BasePermission):
    """doctor, nurse, or lab_technician — can access clinical records."""

    def has_permission(self, request, view):
        return request.user.is_authenticated and getattr(request.user, "is_clinical", False)


class IsAdminOrClinical(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and (
            getattr(request.user, "is_admin_level", False)
            or getattr(request.user, "is_clinical", False)
        )


class CanRegisterPatient(BasePermission):
    """doctor, nurse, receptionist, hospital_admin, super_admin."""

    def has_permission(self, request, view):
        return request.user.is_authenticated and _has_role(
            request.user,
            "doctor",
            "nurse",
            "receptionist",
            "hospital_admin",
            "super_admin",
        )


class CanCreateEncounter(BasePermission):
    """doctor, nurse."""

    def has_permission(self, request, view):
        return request.user.is_authenticated and _has_role(request.user, "doctor", "nurse")


class CanPrescribe(BasePermission):
    """doctor only."""

    def has_permission(self, request, view):
        return request.user.is_authenticated and _has_role(request.user, "doctor")


class CanCreateLabResult(BasePermission):
    """doctor, nurse, lab_technician."""

    def has_permission(self, request, view):
        return request.user.is_authenticated and _has_role(
            request.user, "doctor", "nurse", "lab_technician"
        )


class CanManageStaff(BasePermission):
    """hospital_admin (own hospital) or super_admin (all hospitals)."""

    def has_permission(self, request, view):
        return request.user.is_authenticated and (
            _has_role(request.user, "hospital_admin", "super_admin")
            or getattr(request.user, "is_superuser", False)
        )


class CanManageHospitals(BasePermission):
    """super_admin only for create/edit; any authenticated user for list/view."""

    def has_permission(self, request, view):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return request.user.is_authenticated
        return request.user.is_authenticated and _has_role(request.user, "super_admin")


class CanViewAuditLog(BasePermission):
    """super_admin or hospital_admin."""

    def has_permission(self, request, view):
        return request.user.is_authenticated and (
            _has_role(request.user, "super_admin", "hospital_admin")
            or getattr(request.user, "is_superuser", False)
        )


# ── Phase B permission classes ─────────────────────────────────────────────────


class CanRecordVitals(BasePermission):
    """doctor, nurse."""

    def has_permission(self, request, view):
        return request.user.is_authenticated and _has_role(request.user, "doctor", "nurse")


class CanOrderLabTest(BasePermission):
    """doctor, nurse."""

    def has_permission(self, request, view):
        return request.user.is_authenticated and _has_role(request.user, "doctor", "nurse")


class CanResultLabOrder(BasePermission):
    """lab_technician (and doctor/nurse can create results directly)."""

    def has_permission(self, request, view):
        return request.user.is_authenticated and _has_role(
            request.user, "lab_technician", "doctor", "nurse"
        )


class CanAdministerMedication(BasePermission):
    """nurse only for administration; doctor can read MAR."""

    def has_permission(self, request, view):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return request.user.is_authenticated and _has_role(
                request.user, "doctor", "nurse", "hospital_admin", "super_admin"
            )
        return request.user.is_authenticated and _has_role(request.user, "nurse")


class CanManageAppointments(BasePermission):
    """receptionist, doctor, nurse, hospital_admin, super_admin."""

    def has_permission(self, request, view):
        return request.user.is_authenticated and _has_role(
            request.user,
            "receptionist",
            "doctor",
            "nurse",
            "hospital_admin",
            "super_admin",
        )


class CanManageReferrals(BasePermission):
    """doctor, hospital_admin, super_admin."""

    def has_permission(self, request, view):
        return request.user.is_authenticated and _has_role(
            request.user, "doctor", "hospital_admin", "super_admin"
        )


class CanManageWards(BasePermission):
    """hospital_admin/super_admin for writes; all authenticated for reads."""

    def has_permission(self, request, view):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return request.user.is_authenticated
        return request.user.is_authenticated and _has_role(
            request.user, "hospital_admin", "super_admin"
        )


class CanManageShifts(BasePermission):
    """nurse (own shifts), hospital_admin/super_admin (all shifts)."""

    def has_permission(self, request, view):
        return request.user.is_authenticated and _has_role(
            request.user, "nurse", "hospital_admin", "super_admin"
        )


class CanQueryAI(BasePermission):
    """Clinical and admin roles may query the AI assistant."""

    def has_permission(self, request, view):
        return request.user.is_authenticated and _has_role(
            request.user,
            "doctor",
            "nurse",
            "hospital_admin",
            "super_admin",
        )


class CanViewAlerts(BasePermission):
    """Any authenticated user (alerts are scoped by workspace in the view)."""

    def has_permission(self, request, view):
        return request.user.is_authenticated


class CanResolveAlerts(BasePermission):
    """doctor, nurse."""

    def has_permission(self, request, view):
        return request.user.is_authenticated and _has_role(request.user, "doctor", "nurse")


from rest_framework.throttling import ScopedRateThrottle, UserRateThrottle  # noqa: F401 — re-exported for views


class BreakGlassThrottle(UserRateThrottle):
    """
    Rate-limits break-glass requests to 5 per hour per user.
    Prevents a compromised or abusive account from issuing unlimited
    emergency access grants across patients.
    """
    rate = "5/hour"


def has_hospital_access(user, targets) -> bool:
    """
    Check if user has hospital-scoped access to target hospital(s).

    Parameters
    ----------
    user : User instance
    targets : Hospital instance, Hospital ID, None, or iterable thereof.

    Returns True if:
      1. user is authenticated AND super_admin (or is_superuser)
      2. user is authenticated, has a non-null user.hospital, and user.hospital
         matches any valid non-null target in `targets`.
    Returns False otherwise.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False

    if _has_role(user, "super_admin") or getattr(user, "is_superuser", False):
        return True

    user_hospital = getattr(user, "hospital", None)
    if user_hospital is None:
        return False

    user_hospital_id = getattr(user_hospital, "pk", user_hospital)

    if targets is None:
        return False

    if not isinstance(targets, (list, tuple, set)):
        targets_list = [targets]
    else:
        targets_list = list(targets)

    for target in targets_list:
        if target is None:
            continue
        target_id = getattr(target, "pk", target)
        if user_hospital_id == target_id:
            return True

    return False


