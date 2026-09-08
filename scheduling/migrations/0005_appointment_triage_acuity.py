import re
from django.db import migrations, models


def backfill_triage_acuity(apps, schema_editor):
    Appointment = apps.get_model("scheduling", "Appointment")
    for appt in Appointment.objects.filter(appointment_type="emergency", triage_acuity__isnull=True):
        text = appt.notes or appt.reason or ""
        match = re.search(r"\[Triage:\s*(RED|ORANGE|YELLOW|GREEN)\]", text, re.IGNORECASE)
        if match:
            appt.triage_acuity = match.group(1).upper()
            appt.save(update_fields=["triage_acuity"])


class Migration(migrations.Migration):

    dependencies = [
        ('scheduling', '0004_alter_appointment_notes_alter_appointment_reason'),
    ]

    operations = [
        migrations.AddField(
            model_name='appointment',
            name='triage_acuity',
            field=models.CharField(blank=True, choices=[('RED', 'Red - Resuscitation'), ('ORANGE', 'Orange - Emergent'), ('YELLOW', 'Yellow - Urgent'), ('GREEN', 'Green - Non-urgent')], db_index=True, help_text='South African / Manchester Triage Scale acuity level (RED, ORANGE, YELLOW, GREEN).', max_length=10, null=True),
        ),
        migrations.RunPython(backfill_triage_acuity, migrations.RunPython.noop),
    ]

