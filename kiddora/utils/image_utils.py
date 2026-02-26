from PIL import Image
from io import BytesIO
from django.core.files.base import ContentFile


# -----------------------------
# IMAGE PROCESSING
# -----------------------------
def process_image(file, size=(800, 800)):
    img = Image.open(file)
    img = img.convert("RGB")
    img.thumbnail(size)

    buffer = BytesIO()
    img.save(buffer, format="JPEG", quality=85)
    return ContentFile(buffer.getvalue(), name=file.name)
