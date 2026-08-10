"""
Django settings for the Secure Centralized EMR System.

Reads all secrets from environment variables (or .env file) via django-environ.
"""

from pathlib import Path

import environ

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    FIELD_ENCRYPTION_KEYS=(str, ""),  # comma-separated keys for rotation (new key first)
    FIELD_ENCRYPTION_KEY=(str, ""),  # legacy single-key fallback
    BLIND_INDEX_KEY=(str, ""),
    MFA_ENFORCED=(bool, None),  # None = auto (True unless DEBUG)
    AXES_FAILURE_LIMIT=(int, 5),
    TRUSTED_PROXY_COUNT=(int, 1),  # number of trusted reverse proxies in front of this app
    # Cache (shared across Gunicorn workers — required for correct rate limiting)
    REDIS_URL=(str, ""),  # e.g. redis://localhost:6379/0
    # AI assistant settings (Phase E)
    AI_PROVIDER=(str, "ollama"),  # "gemini" | "ollama"
    GEMINI_API_KEY=(str, ""),
    GEMINI_MODEL=(str, "gemini-2.5-flash"),
    OLLAMA_BASE_URL=(str, "http://localhost:11434"),
    OLLAMA_MODEL=(str, "llama3.1:8b"),
)

environ.Env.read_env(BASE_DIR / ".env")

# ---------------------------------------------------------------------------
# Core Django config
# ---------------------------------------------------------------------------
SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")

# ---------------------------------------------------------------------------
# Application definition
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    # Django built-ins
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # MFA (TOTP)
    "django_otp",
    "django_otp.plugins.otp_totp",
    # Brute-force protection
    "axes",
    # REST API
    "rest_framework",
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
    "whitenoise.middleware.WhiteNoiseMiddleware",  # static files in prod
    "core.middleware.SessionInterruptedMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "core.middleware.RLSContextMiddleware",  # set Postgres GUCs for RLS policies
    "django_otp.middleware.OTPMiddleware",  # marks otp_device on request
    "axes.middleware.AxesMiddleware",  # brute-force lockout
    "audit.middleware.AuditMiddleware",  # must come after auth
    "accounts.mfa_middleware.MFAEnforcementMiddleware",  # tiered MFA gate
    "core.middleware.NoCachePHIMiddleware",  # Cache-Control: no-store on PHI pages
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "emr.urls"

_SPA_DIST = BASE_DIR / "frontend" / "dist"
_SPA_DIST_DIRS = [_SPA_DIST] if _SPA_DIST.exists() else []

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"] + _SPA_DIST_DIRS,
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

# In dev: allow Vite dev server as a CSRF trusted origin so the SPA can make
# API calls when running the React dev server on :5173 alongside Django on :8000.
if DEBUG:
    CSRF_TRUSTED_ORIGINS = env.list(
        "CSRF_TRUSTED_ORIGINS",
        default=["http://localhost:5173", "http://127.0.0.1:5173"],
    )
    # Also allow the CSRF cookie to be read cross-origin in dev
    CSRF_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SAMESITE = "Lax"

WSGI_APPLICATION = "emr.wsgi.application"

# ---------------------------------------------------------------------------
# Authentication backends (django-axes requires its backend listed first)
# ---------------------------------------------------------------------------
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]

# ---------------------------------------------------------------------------
# Database — Neon (serverless Postgres) via DATABASE_URL
# ---------------------------------------------------------------------------
DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="sqlite:///db.sqlite3",  # fallback for local dev without Neon
    )
}

# Force SSL for Postgres connections (covers Neon's sslmode=require in the DSN
# and adds it explicitly in case someone forgets to add ?sslmode=require).
if DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql":
    DATABASES["default"].setdefault("OPTIONS", {})
    DATABASES["default"]["OPTIONS"]["sslmode"] = "require"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Cache
#
# A shared cache is required so that rate-limiting (patient search) is
# enforced correctly across all Gunicorn worker processes.
#
# Production: set REDIS_URL in the environment (e.g. redis://localhost:6379/0
# or a managed Redis URL from Railway/Render/Upstash).  The Redis backend
# is built into Django 4.0+ but still requires the `redis` Python package
# (listed in requirements.txt).
#
# Local dev / testing: falls back to LocMemCache (per-process; acceptable for
# a single-worker dev server but not for multi-worker production).
# ---------------------------------------------------------------------------
REDIS_URL = env("REDIS_URL")

if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
        }
    }
else:
    if not DEBUG:
        import warnings
        warnings.warn(
            "REDIS_URL is not set in production (DEBUG=False). "
            "Rate limiting and caching will fall back to per-process LocMemCache, "
            "which is ineffective across multiple Gunicorn workers.",
            RuntimeWarning,
        )
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    }

# ---------------------------------------------------------------------------
# Custom user model
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"

# ---------------------------------------------------------------------------
# Password validation (strong-auth requirement)
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    # NIST SP 800-63B: prefer length over complexity; minimum 12 chars.
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# Auth redirects
# ---------------------------------------------------------------------------
LOGIN_URL = "/spa/login"
LOGIN_REDIRECT_URL = "/spa/"
LOGOUT_REDIRECT_URL = "/spa/login"

# ---------------------------------------------------------------------------
# Email configuration (MFA Email OTP & notifications)
# Default in dev: console backend (prints sent emails to terminal/logs)
# Production: override EMAIL_BACKEND / EMAIL_HOST via environment variables
# ---------------------------------------------------------------------------
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="mEd Security <noreply@hospital.org>")


# ---------------------------------------------------------------------------
# Internationalisation
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# ---------------------------------------------------------------------------
# Media files (patient documents)
# ---------------------------------------------------------------------------
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

STATICFILES_DIRS = [BASE_DIR / "static"]
if _SPA_DIST.exists():
    STATICFILES_DIRS.append(_SPA_DIST)

# Use CompressedStaticFilesStorage (no manifest) so Vite's own fingerprinting
# doesn't clash with Django's manifest rewriting.
STATICFILES_STORAGE = "whitenoise.storage.CompressedStaticFilesStorage"

# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------
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
        # Break-glass is a high-sensitivity action — cap at 5 per hour to limit
        # abuse by a compromised or rogue account.
        "break_glass": "5/hour",
    },
}

# ---------------------------------------------------------------------------
# Field-level encryption keys (Fernet / MultiFernet)
#
# Use FIELD_ENCRYPTION_KEYS (comma-separated, new key first) to support
# key rotation without downtime: new key encrypts, all keys decrypt.
# After rotation run:  python manage.py reencrypt_fields
# See docs/runbook.md for the complete key-rotation and escrow procedure.
#
# FIELD_ENCRYPTION_KEY (single key) is still supported as a legacy fallback.
# ---------------------------------------------------------------------------
FIELD_ENCRYPTION_KEYS = env("FIELD_ENCRYPTION_KEYS", default="")
FIELD_ENCRYPTION_KEY = env("FIELD_ENCRYPTION_KEY")

# ---------------------------------------------------------------------------
# Blind-index key for encrypted-column search (HMAC-SHA256)
# Generate with: python -c "import secrets; print(secrets.token_hex(32))"
# ---------------------------------------------------------------------------
BLIND_INDEX_KEY = env("BLIND_INDEX_KEY", default="")

# ---------------------------------------------------------------------------
# Reverse-proxy trust
# Set TRUSTED_PROXY_COUNT to the number of trusted load-balancer / nginx hops
# in front of this application.  Used by audit/utils.py to select the correct
# IP from X-Forwarded-For (rightmost N entries are proxy-appended and trusted;
# entries to the left are client-supplied and must not be used for audit IPs).
# ---------------------------------------------------------------------------
TRUSTED_PROXY_COUNT = env("TRUSTED_PROXY_COUNT")

# ---------------------------------------------------------------------------
# MFA enforcement
# MFA_ENFORCED=True  → clinical/admin roles MUST pass TOTP each session
# MFA_ENFORCED=False → MFA is available (enrolment UI shown) but not blocked
# Default: True in production (DEBUG=False), False in DEBUG (for demo usability)
# ---------------------------------------------------------------------------
_mfa_env = env("MFA_ENFORCED")
MFA_ENFORCED: bool = _mfa_env if _mfa_env is not None else (not DEBUG)

MFA_REQUIRED_ROLES = frozenset(
    {
        "super_admin",
        "hospital_admin",
        "doctor",
        "nurse",
        "lab_technician",
    }
)

# Trusted-device window (hours): re-prompt at most once per shift per known device.
# Clinicians are re-prompted on new device, window expiry, or sensitive actions.
MFA_TRUSTED_DEVICE_HOURS = env.int("MFA_TRUSTED_DEVICE_HOURS", default=8)

# FHIR API base URL — used in resource references and fullUrl fields
FHIR_BASE_URL = env("FHIR_BASE_URL", default="https://emr.example.com/fhir")

# ---------------------------------------------------------------------------
# AI assistant (Phase E)
# AI_PROVIDER = "gemini" (default, free tier) | "ollama" (local, no PHI leaves server)
# Set GEMINI_API_KEY in .env to enable the Gemini provider.
# For OLLAMA: run Ollama locally and set OLLAMA_BASE_URL / OLLAMA_MODEL.
# ---------------------------------------------------------------------------
AI_PROVIDER = env("AI_PROVIDER")
GEMINI_API_KEY = env("GEMINI_API_KEY")
GEMINI_MODEL = env("GEMINI_MODEL")
OLLAMA_BASE_URL = env("OLLAMA_BASE_URL")
OLLAMA_MODEL = env("OLLAMA_MODEL")

# ---------------------------------------------------------------------------
# django-axes: brute-force login lockout
# ---------------------------------------------------------------------------
AXES_FAILURE_LIMIT = env("AXES_FAILURE_LIMIT")  # lock after N failures
AXES_COOLOFF_TIME = 1  # 1 hour lockout
AXES_LOCKOUT_CALLABLE = "accounts.lockout.axes_lockout_response"
AXES_RESET_ON_SUCCESS = True  # clear failure count on success
AXES_HTTP_RESPONSE_CODE = 403

# ---------------------------------------------------------------------------
# Security headers (activated when DEBUG=False)
# ---------------------------------------------------------------------------
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"
    X_FRAME_OPTIONS = "DENY"

# ---------------------------------------------------------------------------
# Session security
# ---------------------------------------------------------------------------
SESSION_COOKIE_AGE = 3600  # 1 hour idle timeout
SESSION_SAVE_EVERY_REQUEST = True  # reset timer on activity
SESSION_COOKIE_HTTPONLY = True
# CSRF_COOKIE_HTTPONLY must remain False (Django default) so the SPA can read
# the csrftoken cookie via document.cookie in the Axios request interceptor.
# The SESSION cookie above stays HttpOnly — that one must never be JS-readable.
# See: https://docs.djangoproject.com/en/5.2/ref/settings/#csrf-cookie-httponly
CSRF_COOKIE_HTTPONLY = False

# ---------------------------------------------------------------------------
# Structured logging
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{asctime} [{levelname}] {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": env("LOG_LEVEL", default="WARNING"),
    },
    "loggers": {
        "django.security": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "audit": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "axes": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}
