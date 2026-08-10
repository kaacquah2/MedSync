"""
reindex_blind — recompute and persist blind-index hashes for all Patient rows.

Run this after rotating BLIND_INDEX_KEY so that `name_hash` and
`national_id_hash` are recomputed with the new key and saved to the database.

Note on the reencrypt_fields command
-------------------------------------
`reencrypt_fields` also calls patient.save(), but it passes
``update_fields=[<encrypted field names only>]``.  Django's ``update_fields``
means the SQL UPDATE only touches those columns, so the newly-computed hash
attributes are *not* persisted.  This command is the dedicated fix: it saves
with ``update_fields=["name_hash", "national_id_hash"]``, which triggers
Patient.save() → make_blind_index() → super().save(update_fields=[...]).

Typical rotation workflow
--------------------------
1. Set a new BLIND_INDEX_KEY in .env (old key can be dropped immediately — the
   blind index is a one-way HMAC, not a symmetric cipher).
2. Restart the application.
3. Run: python manage.py reindex_blind
   (optionally with --dry-run first to confirm the patient count)
4. Verify search still works: log in, search a patient by name.

See docs/runbook.md §8 for the full key-rotation runbook.
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Recompute name_hash / national_id_hash for every Patient row. "
        "Run after rotating BLIND_INDEX_KEY. See docs/runbook.md §8."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Count rows and print intent without saving anything.",
        )

    def handle(self, *args, **options):
        from django.apps import apps

        dry_run = options["dry_run"]

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — no changes will be saved.\n"))

        try:
            Patient = apps.get_model("patients", "Patient")
        except LookupError:
            self.stderr.write(self.style.ERROR("patients.Patient model not found."))
            return

        qs = Patient.objects.all()
        count = qs.count()
        self.stdout.write(f"  patients.Patient: {count} rows …")

        if dry_run:
            self.stdout.write(self.style.SUCCESS(f"\nWould reindex {count} Patient rows."))
            return

        errors = 0
        processed = 0
        for patient in qs.iterator():
            try:
                # Patient.save() recomputes name_hash and national_id_hash before
                # calling super().save().  Passing update_fields here limits the
                # SQL UPDATE to just those two columns (efficient) while still
                # running the override that recomputes the values.
                patient.save(update_fields=["name_hash", "national_id_hash"])
                processed += 1
            except Exception as exc:
                errors += 1
                self.stderr.write(f"    ERROR on Patient pk={patient.pk}: {exc}")

        status = self.style.ERROR(f"ERRORS: {errors}") if errors else self.style.SUCCESS("OK")
        self.stdout.write(f"    → {status} ({processed} updated)")

        self.stdout.write(self.style.SUCCESS(f"\nReindexed {processed} Patient rows."))
        if errors:
            self.stderr.write(
                self.style.ERROR(
                    f"{errors} errors encountered. "
                    "Confirm BLIND_INDEX_KEY is set correctly in .env."
                )
            )
        else:
            self.stdout.write(
                "  All patients' blind indexes updated with the current key.\n"
                "  Patient search by name and national ID is now consistent."
            )
