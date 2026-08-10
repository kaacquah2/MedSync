from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Add a partial-unique constraint on Bed.current_patient.

    A patient can only be assigned to one bed at a time.  The constraint is
    partial (WHERE current_patient IS NOT NULL) so that multiple beds can
    simultaneously have no patient (NULL ≠ NULL in SQL unique semantics, but
    being explicit avoids Postgres/SQLite behavioural differences).
    """

    dependencies = [
        ("hospitals", "0002_ward_bed"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="bed",
            constraint=models.UniqueConstraint(
                fields=["current_patient"],
                condition=~models.Q(current_patient=None),
                name="bed_unique_current_patient",
            ),
        ),
    ]
