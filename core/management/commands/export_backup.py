import os
import shutil
import tarfile
from datetime import datetime

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Exports database snapshot and media patient documents to a timestamped backup directory."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output-dir",
            type=str,
            default=None,
            help="Destination directory for the backup (default: backups/<timestamp>/).",
        )

    def handle(self, *args, **options):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = options["output_dir"] or os.path.join(settings.BASE_DIR, "backups", timestamp)
        os.makedirs(backup_dir, exist_ok=True)

        self.stdout.write(f"==> Starting mEd backup at {timestamp}...")

        # 1. Backup Database
        vendor = connection.vendor
        if vendor == "sqlite":
            db_name = settings.DATABASES["default"]["NAME"]
            if os.path.exists(db_name):
                dest_file = os.path.join(backup_dir, f"db_{timestamp}.sqlite3")
                self.stdout.write(f"Backing up SQLite database ({db_name})...")
                # Use python's sqlite3 backup API if possible, fallback to copy
                try:
                    import sqlite3

                    src_conn = sqlite3.connect(db_name)
                    dst_conn = sqlite3.connect(dest_file)
                    with dst_conn:
                        src_conn.backup(dst_conn)
                    dst_conn.close()
                    src_conn.close()
                except Exception:
                    shutil.copy2(db_name, dest_file)
                self.stdout.write(self.style.SUCCESS(f"SQLite database backed up to: {dest_file}"))
            else:
                self.stdout.write(self.style.WARNING(f"SQLite file {db_name} not found."))
        elif vendor == "postgresql":
            db_url = os.environ.get("DATABASE_URL")
            dest_file = os.path.join(backup_dir, f"db_{timestamp}.dump")
            if db_url:
                self.stdout.write("Dumping PostgreSQL database using DATABASE_URL...")
                ret = os.system(f'pg_dump "{db_url}" --format=custom --file="{dest_file}"')
                if ret == 0:
                    self.stdout.write(self.style.SUCCESS(f"PostgreSQL dump saved to: {dest_file}"))
                else:
                    self.stdout.write(
                        self.style.WARNING("pg_dump returned non-zero exit code (ensure pg_dump is in PATH).")
                    )
            else:
                self.stdout.write(
                    self.style.WARNING("DATABASE_URL not set; skipping automated pg_dump execution.")
                )

        # 2. Backup Patient Documents
        docs_dir = os.path.join(settings.MEDIA_ROOT, "patient_documents")
        if os.path.exists(docs_dir) and os.listdir(docs_dir):
            archive_path = os.path.join(backup_dir, f"documents_{timestamp}.tar.gz")
            self.stdout.write("Archiving patient documents from media/patient_documents...")
            with tarfile.open(archive_path, "w:gz") as tar:
                tar.add(docs_dir, arcname="patient_documents")
            self.stdout.write(self.style.SUCCESS(f"Patient documents archived to: {archive_path}"))
        else:
            self.stdout.write("No patient documents found to archive in media/patient_documents.")

        self.stdout.write(self.style.SUCCESS(f"==> Backup successfully created at {backup_dir}"))
