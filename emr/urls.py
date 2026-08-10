"""Root URL configuration for the EMR system."""

from django.contrib import admin
from django.db import connection
from django.http import JsonResponse
from django.urls import include, path, re_path
from django.views.generic import RedirectView, TemplateView

from core.error_views import handler_403, handler_404, handler_500

# ── Custom error handlers (activated in production / WSGI mode) ─────────────
handler403 = handler_403
handler404 = handler_404
handler500 = handler_500


def healthz(request):
    """
    /healthz/ — lightweight health-check for Docker and load-balancers.

    Checks:
      - database connectivity
      - Fernet encryption round-trip (encrypt + decrypt with the primary key)

    Returns 200 OK when all checks pass, 503 when any check fails.
    """
    # ── Database ──────────────────────────────────────────────────────────────
    try:
        connection.ensure_connection()
        db_ok = True
        db_error = None
    except Exception as exc:
        db_ok = False
        db_error = str(exc)

    # ── Encryption round-trip ─────────────────────────────────────────────────
    try:
        from core.fields import _get_fernet

        fernet = _get_fernet()
        probe = b"healthz-probe"
        token = fernet.encrypt(probe)
        enc_ok = fernet.decrypt(token) == probe
        enc_error = None
    except Exception as exc:
        enc_ok = False
        enc_error = str(exc)

    all_ok = db_ok and enc_ok
    http_status = 200 if all_ok else 503
    return JsonResponse(
        {
            "status": "ok" if all_ok else "error",
            "database": "connected" if db_ok else db_error,
            "encryption": "ok" if enc_ok else enc_error,
        },
        status=http_status,
    )


_SPA = RedirectView.as_view(url="/spa/", permanent=False)

urlpatterns = [
    # Health-check (no auth required — used by Docker healthcheck + orchestrators)
    path("healthz/", healthz, name="healthz"),
    # Django admin (superuser / SYSTEM_ADMIN only)
    path("admin/", admin.site.urls),
    # ── JSON REST API (consumed by the React SPA) ────────────────────────────
    path("api/", include("api.urls")),
    # ── FHIR read-only endpoints ─────────────────────────────────────────────
    path("fhir/", include("fhir.urls")),
    # ── SPA — serves React index.html for all /spa/* paths ───────────────────
    re_path(r"^spa/.*$", TemplateView.as_view(template_name="index.html"), name="spa"),
    # ── Legacy-route redirects — forward old bookmarks/links to the SPA ──────
    # These stay until all external references are updated, then can be removed.
    path("", _SPA, name="root"),
    path("accounts/", _SPA, name="legacy-accounts"),
    path("hospitals/", _SPA, name="legacy-hospitals"),
    path("patients/", _SPA, name="legacy-patients"),
    path("records/", _SPA, name="legacy-records"),
    path("audit/", _SPA, name="legacy-audit"),
    path("access-denied/", _SPA, name="legacy-access"),
    path("break-glass/", _SPA, name="legacy-break-glass"),
]

# Custom admin site branding
admin.site.site_header = "EMR System — Admin"
admin.site.site_title = "EMR Admin"
admin.site.index_title = "System Administration"
