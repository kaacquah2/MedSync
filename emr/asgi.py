"""ASGI config for the EMR project."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "emr.settings")
application = get_asgi_application()
