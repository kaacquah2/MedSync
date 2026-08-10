from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Schema hardening for clinical records:
      - Composite index on Encounter(patient, created_at) — hot path for
        patient chart tabs and the AI context builder.
      - CheckConstraints on VitalSign fields to reject physiologically
        impossible values at the DB layer.
    """

    dependencies = [
        ("records", "0003_vitalsign_medicationadministration_laborder_and_more"),
    ]

    operations = [
        # Composite index: patient chart tab queries always filter by patient
        # and sort by created_at — without this index they scan every encounter.
        migrations.AddIndex(
            model_name="encounter",
            index=models.Index(
                fields=["patient", "created_at"],
                name="encounter_patient_created_idx",
            ),
        ),
        # VitalSign: sane physiological ranges (NULL allowed — record only what
        # was measured).
        migrations.AddConstraint(
            model_name="vitalsign",
            constraint=models.CheckConstraint(
                check=(
                    models.Q(temperature__isnull=True)
                    | (models.Q(temperature__gte=30.0) & models.Q(temperature__lte=45.0))
                ),
                name="vitalsign_temperature_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="vitalsign",
            constraint=models.CheckConstraint(
                check=(
                    models.Q(heart_rate__isnull=True)
                    | (models.Q(heart_rate__gte=20) & models.Q(heart_rate__lte=300))
                ),
                name="vitalsign_heart_rate_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="vitalsign",
            constraint=models.CheckConstraint(
                check=(
                    models.Q(bp_systolic__isnull=True)
                    | (models.Q(bp_systolic__gte=50) & models.Q(bp_systolic__lte=250))
                ),
                name="vitalsign_bp_systolic_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="vitalsign",
            constraint=models.CheckConstraint(
                check=(
                    models.Q(bp_diastolic__isnull=True)
                    | (models.Q(bp_diastolic__gte=30) & models.Q(bp_diastolic__lte=150))
                ),
                name="vitalsign_bp_diastolic_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="vitalsign",
            constraint=models.CheckConstraint(
                check=(
                    models.Q(spo2__isnull=True) | (models.Q(spo2__gte=50) & models.Q(spo2__lte=100))
                ),
                name="vitalsign_spo2_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="vitalsign",
            constraint=models.CheckConstraint(
                check=(
                    models.Q(pain_score__isnull=True)
                    | (models.Q(pain_score__gte=0) & models.Q(pain_score__lte=10))
                ),
                name="vitalsign_pain_score_range",
            ),
        ),
    ]
