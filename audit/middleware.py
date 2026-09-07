"""
Audit middleware: logs LOGIN and LOGOUT events.

Django's auth views emit user_logged_in / user_logged_out signals; we listen
to those in audit/signals.py for fine-grained control.  The middleware here
is a lightweight holder for the request so signals can access it.
"""

import threading

_local = threading.local()


def get_current_request():
    return getattr(_local, "request", None)


class AuditMiddleware:
    """
    Stores the current request in thread-local storage so that signal handlers
    (which don't receive the request) can call get_current_request().
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _local.request = request
        try:
            return self.get_response(request)
        finally:
            _local.request = None
