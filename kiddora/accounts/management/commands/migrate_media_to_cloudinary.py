import os
from pathlib import Path
from django.core.management.base import BaseCommand
from django.conf import settings
import cloudinary
import cloudinary.uploader

# Force configuration early
cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET'),
    secure=True,
)

class Command(BaseCommand):
    help = 'Migrate existing media files to Cloudinary while preserving folder structure'

    def handle(self, *args, **options):
        media_root = Path(settings.MEDIA_ROOT)
        if not media_root.exists():
            self.stdout.write(self.style.ERROR(f"Media folder not found: {media_root}"))
            return

        self.stdout.write(self.style.SUCCESS(f"Starting migration from: {media_root}"))

        uploaded = 0
        skipped = 0
        errors = 0

        for root, dirs, files in os.walk(media_root):
            for file_name in files:
                if file_name.startswith('.'):  # skip hidden files
                    continue

                local_path = Path(root) / file_name
                relative_path = local_path.relative_to(media_root)
                folder = str(relative_path.parent).replace('\\', '/')  # normalize for Cloudinary

                # Optional: skip very small or non-image files if needed
                if local_path.stat().st_size == 0:
                    self.stdout.write(self.style.WARNING(f"⚠ Skipped empty file: {relative_path}"))
                    skipped += 1
                    continue

                try:
                    result = cloudinary.uploader.upload(
                        str(local_path),
                        folder=folder or None,          # root folder if empty
                        use_filename=True,
                        unique_filename=False,
                        overwrite=True,
                        resource_type='auto',
                        # Optional: add tags for easier management
                        # tags=["migrated", "django-media"]
                    )

                    public_id = result.get('public_id')
                    secure_url = result.get('secure_url')

                    self.stdout.write(
                        self.style.SUCCESS(f"✓ Uploaded: {relative_path} → {public_id} | URL: {secure_url}")
                    )
                    uploaded += 1

                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"✗ Failed {relative_path}: {str(e)}"))
                    errors += 1

        self.stdout.write("\n" + "="*80)
        self.stdout.write(self.style.SUCCESS(
            f"Migration completed!\n"
            f"Uploaded: {uploaded} | Skipped: {skipped} | Errors: {errors}"
        ))
        self.stdout.write("="*80)