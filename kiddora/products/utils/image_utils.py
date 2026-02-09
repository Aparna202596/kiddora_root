from PIL import Image
from django.core.files.base import ContentFile
from django.core.exceptions import ValidationError
import io


# ---------------- VALIDATION ----------------
def validate_image(image):
    if image.size > 2 * 1024 * 1024:
        raise ValidationError("Image size should not exceed 2MB")

    valid_types = ["image/jpeg", "image/png"]
    if image.content_type not in valid_types:
        raise ValidationError("Only JPG and PNG formats are allowed")


# ---------------- PROCESS & RESIZE ----------------
def process_image(image_file, size=(800, 800), quality=90):
    """
    - Converts to RGB
    - Resizes using thumbnail (keeps aspect ratio)
    - Returns Django ContentFile
    """

    validate_image(image_file)

    img = Image.open(image_file)
    img = img.convert("RGB")
    img.thumbnail(size)

    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=quality)

    return ContentFile(
        buffer.getvalue(),
        name=image_file.name
    )
