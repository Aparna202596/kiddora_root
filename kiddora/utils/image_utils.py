from PIL import Image
from io import BytesIO
from django.core.files.uploadedfile import InMemoryUploadedFile
import sys

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
