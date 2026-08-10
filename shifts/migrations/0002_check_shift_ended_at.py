from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Add a CheckConstraint on ShiftRecord ensuring ended_at > started_at
    whenever ended_at is not NULL.  Prevents data entry errors where a
    shift end timestamp precedes its start.
    """

    dependencies = [
        ("shifts", "0001_initial"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="shiftrecord",
            constraint=models.CheckConstraint(
                check=(
                    models.Q(ended_at__isnull=True) | models.Q(ended_at__gt=models.F("started_at"))
                ),
                name="shiftrecord_ended_after_started",
            ),
        ),
    ]
