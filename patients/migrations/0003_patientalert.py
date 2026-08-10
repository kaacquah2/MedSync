"""Migration: add PatientAlert model for cross-hospital allergy/alert sharing."""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.utils import timezone


class Migration(migrations.Migration):
    dependencies = [
        ("patients", "0002_add_blind_index_fields"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("hospitals", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="PatientAlert",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("created_at", models.DateTimeField(default=timezone.now, editable=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "patient",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="alerts",
                        to="patients.patient",
                    ),
                ),
                (
                    "kind",
                    models.CharField(
                        choices=[("ALLERGY", "Allergy"), ("ALERT", "Clinical Alert")],
                        default="ALLERGY",
                        max_length=10,
                    ),
                ),
                (
                    "label",
                    models.TextField(
                        help_text="E.g. Penicillin, Latex, Contrast dye, Peanuts.",
                        verbose_name="Substance / description",
                    ),
                ),
                (
                    "severity",
                    models.CharField(
                        choices=[
                            ("MILD", "Mild"),
                            ("MODERATE", "Moderate"),
                            ("SEVERE", "Severe"),
                            ("LIFE_THREAT", "Life-threatening"),
                        ],
                        default="MODERATE",
                        max_length=15,
                    ),
                ),
                (
                    "reaction",
                    models.TextField(
                        blank=True,
                        help_text="Describe the observed reaction (optional).",
                        verbose_name="Reaction notes",
                    ),
                ),
                (
                    "recorded_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="recorded_alerts",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "recorded_at_hospital",
                    models.ForeignKey(
                        help_text="Hospital where this alert was first recorded. "
                        "Shown to clinicians from other hospitals to make provenance clear.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="recorded_alerts",
                        to="hospitals.hospital",
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        default=True,
                        help_text="Set to False to deactivate (do not delete — preserve audit history).",
                    ),
                ),
            ],
            options={
                "verbose_name": "Patient Alert / Allergy",
                "verbose_name_plural": "Patient Alerts / Allergies",
                "ordering": ["-is_active", "-severity", "-created_at"],
            },
        ),
    ]
