"""
Auth API views — login, logout, me, CSRF, password change.

Session-based auth: React SPA reads the CSRF cookie on /api/csrf/ then
sends X-CSRFToken header on every unsafe request. DRF's SessionAuthentication
enforces this automatically.
"""

from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.middleware.csrf import get_token
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from api.serializers import MeSerializer
from audit.utils import log_action


class CsrfView(APIView):
    """
    GET /api/csrf/
    Returns 204 and ensures the csrftoken cookie is set in the response.
    Must be called before any POST/PATCH/DELETE from the SPA.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        # Force CSRF cookie to be set
        get_token(request)
        return Response({"detail": "CSRF cookie set."})


class MeView(APIView):
    """GET /api/me/ — returns the currently authenticated user's profile."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = MeSerializer(request.user, context={"request": request})
        return Response(serializer.data)

    def patch(self, request):
        """Update own profile (first_name, last_name, phone, bio, email)."""
        allowed = {"first_name", "last_name", "phone", "bio", "email"}
        data = {k: v for k, v in request.data.items() if k in allowed}

        # Validate email format if provided
        if "email" in data:
            from django.core.exceptions import ValidationError as DjangoValidationError
            from django.core.validators import validate_email

            try:
                validate_email(data["email"])
            except DjangoValidationError:
                return Response(
                    {"error": "Enter a valid email address."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        user = request.user
        for attr, value in data.items():
            setattr(user, attr, value)
        user.save(update_fields=list(data.keys()))
        return Response(MeSerializer(user, context={"request": request}).data)


class LoginView(APIView):
    """
    POST /api/auth/login/
    Body: { "username": "...", "password": "..." }

    Delegates to Django's auth + axes backend.  On success returns the
    current user's profile (same as /api/me/).  MFA enforcement is handled
    by the existing MFAEnforcementMiddleware on subsequent requests.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        username = request.data.get("username", "").strip()
        password = request.data.get("password", "")

        if not username or not password:
            return Response(
                {"error": "Username and password are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = authenticate(request, username=username, password=password)
        if user is None:
            # axes already incremented failure count via authenticate()
            return Response(
                {"error": "Invalid username or password."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if not user.is_active:
            return Response(
                {"error": "This account has been deactivated."},
                status=status.HTTP_403_FORBIDDEN,
            )

        login(request, user)
        # Note: the user_logged_in Django signal (audit/signals.py) writes the
        # LOGIN audit entry automatically when login() is called above.
        # We do not call log_action here to avoid a duplicate entry.

        serializer = MeSerializer(user, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class LogoutView(APIView):
    """POST /api/auth/logout/ — ends the current session."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        # Note: the user_logged_out signal (audit/signals.py) writes LOGOUT
        # automatically when logout() is called. Do not call log_action here.
        logout(request)
        return Response({"detail": "Logged out successfully."})


class PasswordChangeView(APIView):
    """POST /api/auth/password/change/ — change own password."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_change"

    def post(self, request):
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError as DjangoValidationError

        old_password = request.data.get("old_password", "")
        new_password = request.data.get("new_password", "")

        if not request.user.check_password(old_password):
            return Response(
                {"error": "Current password is incorrect."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Run all configured AUTH_PASSWORD_VALIDATORS (length, common-password,
        # attribute-similarity, numeric-only) — not just a bare length check.
        try:
            validate_password(new_password, request.user)
        except DjangoValidationError as exc:
            return Response(
                {"error": " ".join(exc.messages)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        request.user.set_password(new_password)
        request.user.save()
        # Keep current session alive after password change
        update_session_auth_hash(request, request.user)
        log_action(request, action="PASSWORD_CHANGE", extra={"via": "api"})
        return Response({"detail": "Password changed successfully."})
