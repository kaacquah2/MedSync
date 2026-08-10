"""
AI Query Log model.

Stores query history for clinical auditing while encrypting PHI-bearing
questions and answers at rest.
"""

from django.conf import settings
from django.db import models

from core.fields import EncryptedTextField
from core.models import TimeStampedModel


class AIQuery(TimeStampedModel):
    """
    Persisted log of AI clinical queries and responses.

    Both question and answer are encrypted at rest using EncryptedTextField
    to prevent leaking Protected Health Information (PHI) in plaintext.
    """

    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.CASCADE,
        related_name="ai_queries",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="ai_queries",
    )
    question = EncryptedTextField(verbose_name="User Question")
    answer = EncryptedTextField(verbose_name="AI Response")
    provider = models.CharField(max_length=20)
    model = models.CharField(max_length=50)
    context_size = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "AI Query Log"
        verbose_name_plural = "AI Query Logs"

    def __str__(self):
        user_str = self.user.username if self.user else "System"
        return f"AI Query by {user_str} for patient {self.patient.universal_id} @ {self.created_at}"
