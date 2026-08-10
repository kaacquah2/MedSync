"""
Migration: add RecoveryCode model for MFA backup codes.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="RecoveryCode",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="recovery_codes",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "code_hash",
                    models.CharField(
                        max_length=64,
                        help_text="SHA-256 hex digest of the one-time recovery code.",
                    ),
                ),
                ("used", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("used_at", models.DateTimeField(null=True, blank=True)),
            ],
            options={
                "verbose_name": "Recovery Code",
                "verbose_name_plural": "Recovery Codes",
                "ordering": ["created_at"],
            },
        ),
    ]
