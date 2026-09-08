"""
Custom User model with role-based access control.

Roles (from narrowest to broadest):
  RECEPTIONIST  — registers patients, basic scheduling
  LAB_TECH      — creates / views lab results
  NURSE         — full clinical record read/write (no prescriptions)
  DOCTOR        — full clinical record read/write including prescriptions
  HOSPITAL_ADMIN — manages staff accounts within their hospital
  SYSTEM_ADMIN  — full system access, audit log, hospital management
"""

import hashlib
import hmac
import secrets

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


def hash_recovery_code(code: str) -> str:
    """Keyed HMAC-SHA256 of the recovery code using SECRET_KEY."""
    key = settings.SECRET_KEY.encode()
    return hmac.new(key, code.strip().encode(), hashlib.sha256).hexdigest()


def hash_email_otp(code: str) -> str:
    """Keyed HMAC-SHA256 of the 6-digit email OTP using SECRET_KEY."""
    key = settings.SECRET_KEY.encode()
    return hmac.new(key, code.strip().encode(), hashlib.sha256).hexdigest()


class User(AbstractUser):
    class Role(models.TextChoices):
        SUPER_ADMIN = "super_admin", "Super Admin"
        HOSPITAL_ADMIN = "hospital_admin", "Hospital Admin"
        DOCTOR = "doctor", "Doctor"
        NURSE = "nurse", "Nurse"
        LAB_TECHNICIAN = "lab_technician", "Lab Technician"
        RECEPTIONIST = "receptionist", "Receptionist"

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.RECEPTIONIST,
    )

    # The hospital this staff member belongs to.
    # Null only for SUPER_ADMIN (super-admin is not tied to a facility).
    hospital = models.ForeignKey(
        "hospitals.Hospital",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="staff",
    )

    phone = models.CharField(max_length=20, blank=True)
    bio = models.TextField(blank=True)

    # Incrementing this value invalidates all existing trusted-device cookies
    # for this user.  Used by the "Sign out everywhere" action.
    mfa_trust_version = models.PositiveSmallIntegerField(
        default=0,
        help_text="Increment to revoke all trusted-device cookies for this user.",
    )

    class Meta:
        verbose_name = "Staff Member"
        verbose_name_plural = "Staff Members"

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.get_role_display()})"

    @property
    def is_clinical(self) -> bool:
        """True for roles that can access clinical records."""
        return self.role in (
            self.Role.DOCTOR,
            self.Role.NURSE,
            self.Role.LAB_TECHNICIAN,
        )

    @property
    def is_super_admin(self) -> bool:
        return self.role == self.Role.SUPER_ADMIN or bool(self.is_superuser)

    @property
    def is_hospital_admin(self) -> bool:
        return self.role == self.Role.HOSPITAL_ADMIN

    @property
    def is_admin_level(self) -> bool:
        return self.role in (self.Role.SUPER_ADMIN, self.Role.HOSPITAL_ADMIN)


# Number of single-use recovery codes generated at MFA enrolment
RECOVERY_CODE_COUNT = 8
RECOVERY_CODE_LENGTH = 10  # chars per code (alphanumeric)


class RecoveryCodeManager(models.Manager):
    def generate_for(self, user) -> list[str]:
        """
        Generate RECOVERY_CODE_COUNT fresh single-use recovery codes for *user*.

        Deletes any existing (used or unused) codes first, then creates new ones.
        Returns a list of plaintext codes (shown to the user once at enrolment).
        """
        # Revoke all existing codes
        self.filter(user=user).delete()

        plaintext_codes = []
        for _ in range(RECOVERY_CODE_COUNT):
            code = secrets.token_urlsafe(RECOVERY_CODE_LENGTH)[:RECOVERY_CODE_LENGTH]
            code_hash = hash_recovery_code(code)
            self.create(user=user, code_hash=code_hash)
            plaintext_codes.append(code)

        return plaintext_codes

    def verify_and_consume(self, user, code: str) -> bool:
        """
        Check whether *code* is a valid unused recovery code for *user*.
        If valid, marks it used and returns True.  Returns False otherwise.
        """
        clean_code = code.strip()
        # Primary check: Keyed HMAC-SHA256
        hmac_hash = hash_recovery_code(clean_code)
        try:
            rc = self.get(user=user, code_hash=hmac_hash, used=False)
        except self.model.DoesNotExist:
            # Fallback check: Legacy unsalted SHA-256 for codes created prior to migration
            legacy_hash = hashlib.sha256(clean_code.encode()).hexdigest()
            try:
                rc = self.get(user=user, code_hash=legacy_hash, used=False)
            except self.model.DoesNotExist:
                return False

        rc.used = True
        rc.used_at = timezone.now()
        rc.save(update_fields=["used", "used_at"])
        return True


class RecoveryCode(models.Model):
    """
    A single-use MFA recovery code for a user.

    Generated at MFA enrolment; hashed at rest (SHA-256).
    Used when the user loses access to their authenticator app.

    Each code can be used at most once (used=True after consumption).
    """

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="recovery_codes",
    )
    code_hash = models.CharField(
        max_length=64,
        help_text="SHA-256 hex digest of the one-time recovery code.",
    )
    used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True, blank=True)

    objects = RecoveryCodeManager()

    class Meta:
        ordering = ["created_at"]
        verbose_name = "Recovery Code"
        verbose_name_plural = "Recovery Codes"

    def __str__(self):
        status = "used" if self.used else "active"
        return f"RecoveryCode({self.user.username}, {status})"


EMAIL_OTP_EXPIRY_MINUTES = 10
EMAIL_OTP_MAX_ATTEMPTS = 5


class EmailOTPManager(models.Manager):
    def generate_for(self, user) -> str:
        """
        Generate a fresh 6-digit Email OTP for *user*, expiring in 10 minutes.
        Deletes previous unexpired unused Email OTPs for this user first.
        Returns the 6-digit plaintext OTP string to be sent via email.
        """
        self.filter(user=user, used=False).delete()

        code_int = secrets.randbelow(1000000)
        plaintext_code = f"{code_int:06d}"
        code_hash = hash_email_otp(plaintext_code)
        expires_at = timezone.now() + timezone.timedelta(minutes=EMAIL_OTP_EXPIRY_MINUTES)

        self.create(user=user, code_hash=code_hash, expires_at=expires_at, attempts=0)
        return plaintext_code

    def verify_and_consume(self, user, code: str) -> bool:
        """
        Check whether *code* is a valid unexpired Email OTP for *user*.
        If valid, marks it used and returns True. Returns False otherwise.
        Burns the OTP if failed attempts reach EMAIL_OTP_MAX_ATTEMPTS (5).
        """
        code_str = code.strip()
        if not code_str or not code_str.isdigit() or len(code_str) != 6:
            return False

        now = timezone.now()
        otp = self.filter(user=user, used=False, expires_at__gt=now).order_by("-created_at").first()
        if not otp:
            return False

        if otp.attempts >= EMAIL_OTP_MAX_ATTEMPTS:
            otp.used = True
            otp.used_at = now
            otp.save(update_fields=["used", "used_at"])
            return False

        code_hash = hash_email_otp(code_str)
        legacy_hash = hashlib.sha256(code_str.encode()).hexdigest()
        if secrets.compare_digest(code_hash, otp.code_hash) or secrets.compare_digest(legacy_hash, otp.code_hash):
            otp.used = True
            otp.used_at = now
            otp.save(update_fields=["used", "used_at"])
            return True

        otp.attempts += 1
        if otp.attempts >= EMAIL_OTP_MAX_ATTEMPTS:
            otp.used = True
            otp.used_at = now
            otp.save(update_fields=["attempts", "used", "used_at"])
        else:
            otp.save(update_fields=["attempts"])
        return False


class EmailOTP(models.Model):
    """
    A temporary 6-digit Email One-Time Password (OTP) for MFA verification.
    Valid for 10 minutes; hashed at rest using keyed HMAC-SHA256 (SECRET_KEY).
    """

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="email_otps",
    )
    code_hash = models.CharField(
        max_length=64,
        help_text="Keyed HMAC-SHA256 hex digest of the 6-digit email OTP.",
    )
    attempts = models.PositiveSmallIntegerField(
        default=0,
        help_text="Number of failed verification attempts. Burned after 5.",
    )
    used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    objects = EmailOTPManager()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Email OTP"
        verbose_name_plural = "Email OTPs"

    def __str__(self):
        status = "used" if self.used else "active"
        return f"EmailOTP({self.user.username}, {status})"
