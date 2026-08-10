"""Shared abstract base models."""

from django.db import models
from django.utils import timezone


class TimeStampedModel(models.Model):
    """Abstract base that adds created_at and updated_at to every subclass."""

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
