from django.core.management.base import BaseCommand
from django.conf import settings
import os
import shutil


class Command(BaseCommand):
    help = "Create a weekly backup of the SQLite database"

    def handle(self, *args, **options):
        db_path = settings.DATABASES["default"]["NAME"]

        if not os.path.exists(db_path):
            self.stdout.write(
                self.style.WARNING(f"Database file does not exist: {db_path}")
            )
            return

        backup_dir = os.path.join(os.path.dirname(db_path), "backups")

        os.makedirs(backup_dir, exist_ok=True)

        backup_filename = getattr(settings, "BACKUP_FILENAME", "db_backup.sqlite3")
        backup_path = os.path.join(backup_dir, backup_filename)

        shutil.copy2(db_path, backup_path)

        self.stdout.write(
            self.style.SUCCESS(f"Successfully created backup at {backup_path}")
        )
