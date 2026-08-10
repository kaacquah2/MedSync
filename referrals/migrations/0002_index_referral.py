from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Add a composite index on Referral(to_hospital, status).

    The receiving-hospital worklist always filters on to_hospital + status;
    without this index that query scans the whole referrals table.
    """

    dependencies = [
        ("referrals", "0001_initial"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="referral",
            index=models.Index(
                fields=["to_hospital", "status"],
                name="referral_to_hospital_status_idx",
            ),
        ),
    ]
