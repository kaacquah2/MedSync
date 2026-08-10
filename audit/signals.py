"""
Django signal handlers for automatic audit logging.

Registered in core/apps.py → ready().
"""

from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver


@receiver(user_logged_in)
def on_login(sender, request, user, **kwargs):
    from .utils import log_action

    log_action(request, action="LOGIN", extra={"username": user.username})


@receiver(user_logged_out)
def on_logout(sender, request, user, **kwargs):
    from .utils import log_action

    if user:
        log_action(request, action="LOGOUT", extra={"username": user.username})
