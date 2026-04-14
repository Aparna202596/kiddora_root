import os
from pathlib import Path
from django.core.management.base import BaseCommand
from django.conf import settings
import cloudinary
import cloudinary.uploader

# === Force Cloudinary configuration BEFORE any upload ===
cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET'),
    secure=True,
)

class Command(BaseCommand):
    help = 'Migrate existing media files to Cloudinary while preserving exact folder structure'

    def handle(self, *args, **options):
        media_root = Path(settings.MEDIA_ROOT)
        
        if not media_root.exists():
            self.stdout.write(self.style.ERROR(f"Media folder not found: {media_root}"))
            return

        self.stdout.write(self.style.SUCCESS(f"Starting migration from: {media_root}"))
        
        uploaded = 0
        errors = 0

        for root, dirs, files in os.walk(media_root):
            for file_name in files:
                if file_name.startswith('.'):  # skip hidden files
                    continue
                
                local_path = Path(root) / file_name
                relative_path = local_path.relative_to(media_root)
                
                try:
                    result = cloudinary.uploader.upload(
                        str(local_path),
                        folder=str(relative_path.parent),   # keeps banners/, product_images/, profile_images/, etc.
                        use_filename=True,
                        unique_filename=False,
                        overwrite=True,
                        resource_type='auto'
                    )
                    
                    self.stdout.write(self.style.SUCCESS(f"✓ Uploaded: {relative_path}"))
                    uploaded += 1
                    
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"✗ Failed {relative_path}: {str(e)}"))
                    errors += 1

        self.stdout.write("\n" + "="*80)
        self.stdout.write(self.style.SUCCESS(f"Migration completed! Uploaded: {uploaded} files | Errors: {errors}"))
        self.stdout.write("="*80)