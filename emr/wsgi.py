"""WSGI config for the EMR project."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "emr.settings")
application = get_wsgi_application()
