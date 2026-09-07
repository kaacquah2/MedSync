"""
Test settings — used by pytest-django via conftest.py.

Uses in-memory SQLite and a fixed encryption key so tests run without
a Neon connection and without depending on .env.
"""

import os
from pathlib import Path

import environ

env = environ.Env()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "test-secret-key-do-not-use-in-production"
DEBUG = True
ALLOWED_HOSTS = ["*"]

# Default to in-memory SQLite for fast, isolated test runs without external deps.
# If DATABASE_URL is explicitly set (e.g. CI Postgres service or local test Postgres),
# connect to it instead.
if os.environ.get("DATABASE_URL"):
    DATABASES = {"default": env.db("DATABASE_URL")}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",
        }
    }

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # MFA
    "django_otp",
    "django_otp.plugins.otp_totp",
    # Brute-force
    "axes",
    # Project apps
    "core.apps.CoreConfig",
    "accounts.apps.AccountsConfig",
    "hospitals.apps.HospitalsConfig",
    "patients.apps.PatientsConfig",
    "records.apps.RecordsConfig",
    "audit.apps.AuditConfig",
    "access.apps.AccessConfig",
    "api.apps.ApiConfig",
    # Phase B — new clinical domains
    "scheduling.apps.SchedulingConfig",
    "referrals.apps.ReferralsConfig",
    "shifts.apps.ShiftsConfig",
    # Phase E — AI assistant
    "ai.apps.AiConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "core.middleware.SessionInterruptedMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "core.middleware.RLSContextMiddleware",  # no-op on SQLite
    "django_otp.middleware.OTPMiddleware",
    "axes.middleware.AxesMiddleware",
    "audit.middleware.AuditMiddleware",
    "accounts.mfa_middleware.MFAEnforcementMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "emr.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]

AUTH_PASSWORD_VALIDATORS = []  # no min-length in tests

LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/accounts/login/"

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = []

# ── Fixed test encryption key (valid Fernet key — 32 URL-safe base64 bytes) ──
# Generated via: Fernet.generate_key()
FIELD_ENCRYPTION_KEY = "YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWE="

# ── Fixed blind-index key for tests ────────────────────────────────────────
BLIND_INDEX_KEY = "test-blind-index-key-not-for-production-use-xxxxxxxxxxxxxxxxxxx"

# ── MFA: off in tests (avoid TOTP requirements blocking test flows) ─────────
MFA_ENFORCED = False
MFA_REQUIRED_ROLES = frozenset(
    {
        "super_admin",
        "hospital_admin",
        "doctor",
        "nurse",
        "lab_technician",
    }
)

# ── axes: disable lockout during tests ──────────────────────────────────────
AXES_ENABLED = False
AXES_FAILURE_LIMIT = 100
AXES_COOLOFF_TIME = None
AXES_LOCKOUT_CALLABLE = None
AXES_RESET_ON_SUCCESS = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGGING = {"version": 1, "disable_existing_loggers": True}

# AI (disabled in tests)
AI_PROVIDER = "ollama"
GEMINI_API_KEY = ""
GEMINI_MODEL = "gemini-2.0-flash"
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "llama3.1:8b"
ALLOW_EXTERNAL_AI_IN_PRODUCTION = True

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "EXCEPTION_HANDLER": "api.exceptions.emr_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/day",
        "user": "1000/hour",
        "ai_query": "30/hour",
        "record_creation": "60/minute",
        "document_upload": "10/minute",
        "login": "10/minute",
        "mfa_verify": "10/minute",
        "password_change": "5/minute",
        "break_glass": "5/hour",
    },
}

TESTING = True
AUDIT_CHAIN_HMAC_KEY = None
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "test_media"
