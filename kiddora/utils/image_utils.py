from PIL import Image
from django.core.exceptions import ValidationError

def validate_image(image):
    if image.size > 2 * 1024 * 1024:
        raise ValidationError("Image size should not exceed 2MB")

    valid_types = ["image/jpeg", "image/png"]
    if image.content_type not in valid_types:
        raise ValidationError("Only JPG and PNG formats are allowed")

def resize_image(image_path, size=(800, 800)):
    img = Image.open(image_path)
    img = img.convert("RGB")
    img.thumbnail(size)
    img.save(image_path, quality=85)
