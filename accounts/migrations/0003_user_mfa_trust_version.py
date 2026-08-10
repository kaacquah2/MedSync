from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_recoverycode"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="mfa_trust_version",
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text="Increment to revoke all trusted-device cookies for this user.",
            ),
        ),
    ]
