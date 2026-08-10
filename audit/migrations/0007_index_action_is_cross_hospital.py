from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Add indexes on AuditLog.action and AuditLog.is_cross_hospital.

    The cross-hospital compliance filter was previously a full-table scan;
    these indexes make both the action filter and is_cross_hospital=True
    queries O(log n) instead of O(n).
    """

    dependencies = [
        ("audit", "0006_alter_auditlog_action"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="auditlog",
            index=models.Index(fields=["action"], name="auditlog_action_idx"),
        ),
        migrations.AddIndex(
            model_name="auditlog",
            index=models.Index(
                fields=["is_cross_hospital"],
                name="auditlog_cross_hospital_idx",
            ),
        ),
    ]
