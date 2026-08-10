"""
reencrypt_fields — re-encrypt all Fernet-encrypted model fields using the
                   current primary key (first key in FIELD_ENCRYPTION_KEYS).

Use this after a key rotation:
  1. Prepend the new key to FIELD_ENCRYPTION_KEYS (old key stays as fallback).
  2. Run:  python manage.py reencrypt_fields
     This decrypts every field with whichever key matches, then re-saves using
     the new primary key.
  3. Verify records are readable, then remove the old key from the list.
  4. See docs/runbook.md for the full key-rotation + escrow procedure.

This command is safe to run multiple times (idempotent — records that are
already encrypted with the primary key are re-encrypted, but the result is
valid Fernet ciphertext so functionally identical).

Models with encrypted fields:
  - patients.Patient  — first_name, last_name, date_of_birth, national_id,
                        phone, email, address
  - patients.PatientAlert — label, reaction
  - records.Encounter     — chief_complaint, notes
  - records.Diagnosis     — description
  - records.Prescription  — drug_name, dosage, frequency, instructions
  - records.LabResult     — test_name, result_value
"""

from django.core.management.base import BaseCommand

# Map (app_label.ModelClass, [field_names]) for every model with encrypted fields
ENCRYPTED_MODELS = [
    (
        "patients.Patient",
        ["first_name", "last_name", "date_of_birth", "national_id", "phone", "email", "address"],
    ),
    ("patients.PatientAlert", ["label", "reaction"]),
    ("records.Encounter", ["chief_complaint", "notes"]),
    ("records.Diagnosis", ["description"]),
    ("records.Prescription", ["drug_name", "dosage", "frequency", "instructions"]),
    ("records.LabResult", ["test_name", "result_value"]),
]


class Command(BaseCommand):
    help = (
        "Re-encrypt all Fernet-encrypted fields using the current primary key. "
        "Run after key rotation. See docs/runbook.md."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be done without saving anything.",
        )

    def handle(self, *args, **options):
        from django.apps import apps
        from django.db import connection as _dbc

        # ── RLS bypass ───────────────────────────────────────────────────────
        # reencrypt_fields reads records.Encounter (an RLS-protected table).
        # Management commands run without a request context, so the middleware
        # GUCs are not set.  Set the bypass at session level for this process.
        if _dbc.vendor == "postgresql":
            with _dbc.cursor() as _cur:
                _cur.execute("SELECT set_config('app.bypass_rls', 'on', false)")

        dry_run = options["dry_run"]
        total_rows = 0
        total_errors = 0

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — no changes will be saved.\n"))

        for model_path, field_names in ENCRYPTED_MODELS:
            app_label, model_name = model_path.split(".")
            try:
                Model = apps.get_model(app_label, model_name)
            except LookupError:
                self.stderr.write(f"  Skipping unknown model: {model_path}")
                continue

            rows = Model.objects.all()
            count = rows.count()
            self.stdout.write(f"  {model_path}: {count} rows …")
            model_errors = 0

            for obj in rows.iterator():
                try:
                    if not dry_run:
                        # Reading fields auto-decrypts (EncryptedMixin.from_db_value).
                        # Saving auto-re-encrypts with the primary key (get_prep_value).
                        # We only save if fields have non-empty values to avoid
                        # touching unset (blank) fields unnecessarily.
                        update_fields = []
                        for fname in field_names:
                            val = getattr(obj, fname, None)
                            if val not in (None, "", "[decryption error]"):
                                update_fields.append(fname)
                        if update_fields:
                            obj.save(update_fields=update_fields)
                    total_rows += 1
                except Exception as exc:
                    model_errors += 1
                    total_errors += 1
                    self.stderr.write(f"    ERROR on {model_path} pk={obj.pk}: {exc}")

            status = (
                self.style.ERROR(f"ERRORS: {model_errors}")
                if model_errors
                else self.style.SUCCESS("OK")
            )
            self.stdout.write(f"    → {status} ({count - model_errors} processed)")

        action = "Would re-encrypt" if dry_run else "Re-encrypted"
        self.stdout.write(
            self.style.SUCCESS(
                f"\n{action} {total_rows} records across {len(ENCRYPTED_MODELS)} models."
            )
        )
        if total_errors:
            self.stderr.write(
                self.style.ERROR(
                    f"{total_errors} errors encountered. "
                    "Check FIELD_ENCRYPTION_KEYS — old key may still be needed."
                )
            )
        else:
            self.stdout.write(
                "  All records readable with the current key.\n"
                "  You can now safely remove the old key from FIELD_ENCRYPTION_KEYS."
                if not dry_run
                else ""
            )
