import sys
from io import BytesIO

from django.core.files.uploadedfile import InMemoryUploadedFile
from PIL import Image


# -----------------------------
# IMAGE PROCESSING
# -----------------------------
def process_image(file, size=(800, 800)):
    img = Image.open(file)
    img = img.convert("RGB")
    output = BytesIO()
    img.save(output, format="JPEG", quality=85)
    output.seek(0)

    return InMemoryUploadedFile(
        output,
        "ImageField",
        file.name,
        "image/jpeg",
        sys.getsizeof(output),
        None,
    )
