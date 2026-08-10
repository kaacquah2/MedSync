from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Schema hardening for scheduling:
      - Composite index on Appointment(hospital, scheduled_for, status) —
        the daily worklist query filters on all three columns.
      - CheckConstraint: duration_minutes > 0 (zero-duration appointments
        are nonsensical and indicate a data entry error).
    """

    dependencies = [
        ("scheduling", "0001_initial"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="appointment",
            index=models.Index(
                fields=["hospital", "scheduled_for", "status"],
                name="appointment_hospital_schedule_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="appointment",
            constraint=models.CheckConstraint(
                check=models.Q(duration_minutes__gt=0),
                name="appointment_duration_positive",
            ),
        ),
    ]
