"""Custom DRF exception handler — wraps default handler for consistent JSON shape."""

from rest_framework import status
from rest_framework.exceptions import NotAuthenticated
from rest_framework.response import Response
from rest_framework.views import exception_handler


def emr_exception_handler(exc, context):
    """
    Return JSON errors in a consistent shape:
      { "error": "...", "status_code": <n> }

    Special cases:
      NotAuthenticated  → 401 (not 403) so the SPA axios interceptor can
                          redirect to /spa/login on session expiry.  DRF's
                          SessionAuthentication normally returns 403 here
                          (no WWW-Authenticate challenge), which the client
                          cannot distinguish from RBAC 403s.
    """
    response = exception_handler(exc, context)

    if response is not None:
        # Reclassify unauthenticated errors as 401 so the SPA can react
        if isinstance(exc, NotAuthenticated):
            response.status_code = 401

        data = response.data
        # Normalise DRF's varying shapes to { error, status_code }
        data = response.data
        # Normalise DRF's varying shapes to include status_code
        if isinstance(data, dict):
            if "detail" in data:
                response.data = {
                    "error": str(data["detail"]),
                    "status_code": response.status_code,
                }
            else:
                response.data = dict(data)
                response.data["status_code"] = response.status_code
        elif isinstance(data, list):
            error_msg = data[0] if data else "An error occurred."
            response.data = {
                "error": str(error_msg),
                "status_code": response.status_code,
            }
        else:
            response.data = {
                "error": str(data),
                "status_code": response.status_code,
            }
    else:
        # Unhandled exception — return 500
        response = Response(
            {"error": "An unexpected server error occurred.", "status_code": 500},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return response

