from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("patients", "0001_initial"),
        ("access", "0003_alter_breakglassaccess_actor"),
    ]

    operations = [
        migrations.AlterField(
            model_name="breakglassaccess",
            name="patient",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="break_glass_accesses",
                to="patients.patient",
            ),
        ),
    ]
