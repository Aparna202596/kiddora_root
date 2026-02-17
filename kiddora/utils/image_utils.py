from PIL import Image
from django.core.files.base import ContentFile
from django.core.exceptions import ValidationError
import io
import json

# VALIDATION FUNCTIONS

def validate_image(image, max_size_mb=5, allowed_types=None):

    if allowed_types is None:
        allowed_types = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
    
    # Check file size
    max_size_bytes = max_size_mb * 1024 * 1024
    if image.size > max_size_bytes:
        raise ValidationError(f"Image size should not exceed {max_size_mb}MB")
    
    # Check file type
    if image.content_type not in allowed_types:
        allowed_str = ', '.join([t.split('/')[-1].upper() for t in allowed_types])
        raise ValidationError(f"Only {allowed_str} formats are allowed")
    
    return True


def validate_profile_image(image):
    
    return validate_image(image, max_size_mb=5)


def validate_product_image(image, min_dimension=300):
    
    # First do basic validation (size and type)
    validate_image(image, max_size_mb=10)
    
    # Check minimum dimensions
    img = Image.open(image)
    width, height = img.size
    
    if width < min_dimension or height < min_dimension:
        raise ValidationError(f"Product image must be at least {min_dimension}x{min_dimension} pixels. Current size: {width}x{height}")
    
    return True

# RESIZE FUNCTIONS

def resize_image(image_file, size=(800, 800), keep_aspect_ratio=True, quality=90):
    
    validate_image(image_file)
    
    img = Image.open(image_file)
    img = img.convert("RGB")
    
    if keep_aspect_ratio:
        # Use thumbnail to maintain aspect ratio
        img.thumbnail(size, Image.Resampling.LANCZOS)
    else:
        # Force resize to exact dimensions
        img = img.resize(size, Image.Resampling.LANCZOS)
    
    # Save to buffer
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=quality)
    buffer.seek(0)
    
    # Generate new filename
    original_name = image_file.name
    if '.' in original_name:
        name_parts = original_name.rsplit('.', 1)
        new_name = f"{name_parts[0]}_resized.jpg"
    else:
        new_name = f"{original_name}_resized.jpg"
    
    return ContentFile(buffer.getvalue(), name=new_name)


def create_thumbnail(image_file, size=(150, 150), quality=85):
    
    return resize_image(image_file, size=size, keep_aspect_ratio=True, quality=quality)

# CROP FUNCTIONS

def crop_image(image_file, crop_data, output_size=None, quality=90):
    
    validate_image(image_file)
    
    img = Image.open(image_file)
    img = img.convert("RGB")
    
    orig_width, orig_height = img.size
    
    # Parse crop coordinates
    try:
        x = int(float(crop_data.get('x', 0)))
        y = int(float(crop_data.get('y', 0)))
        crop_width = int(float(crop_data.get('width', orig_width)))
        crop_height = int(float(crop_data.get('height', orig_height)))
        
        # Ensure coordinates are within bounds
        x = max(0, min(x, orig_width - 1))
        y = max(0, min(y, orig_height - 1))
        crop_width = min(crop_width, orig_width - x)
        crop_height = min(crop_height, orig_height - y)
        
        # Crop the image
        img = img.crop((x, y, x + crop_width, y + crop_height))
    except (ValueError, TypeError, AttributeError):
        # If crop data is invalid, return original image
        pass
    
    # Optionally resize after cropping
    if output_size:
        img = img.resize(output_size, Image.Resampling.LANCZOS)
    
    # Save to buffer
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=quality)
    buffer.seek(0)
    
    # Generate new filename
    original_name = image_file.name
    if '.' in original_name:
        name_parts = original_name.rsplit('.', 1)
        new_name = f"{name_parts[0]}_cropped.jpg"
    else:
        new_name = f"{original_name}_cropped.jpg"
    
    return ContentFile(buffer.getvalue(), name=new_name)

# COMBINED PROCESSING FUNCTIONS

def process_image(image_file, crop_data=None, resize_to=None, max_size=(1200, 1200), quality=90):
    
    validate_image(image_file)
    
    img = Image.open(image_file)
    img = img.convert("RGB")
    
    # First, resize if larger than max_size (maintaining aspect ratio)
    if max_size:
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
    
    orig_width, orig_height = img.size
    
    # Apply crop if provided
    if crop_data:
        try:
            x = int(float(crop_data.get('x', 0)))
            y = int(float(crop_data.get('y', 0)))
            crop_width = int(float(crop_data.get('width', orig_width)))
            crop_height = int(float(crop_data.get('height', orig_height)))
            
            # Ensure coordinates are within bounds
            x = max(0, min(x, orig_width - 1))
            y = max(0, min(y, orig_height - 1))
            crop_width = min(crop_width, orig_width - x)
            crop_height = min(crop_height, orig_height - y)
            
            img = img.crop((x, y, x + crop_width, y + crop_height))
        except (ValueError, TypeError, AttributeError):
            pass
    
    # Apply final resize if provided
    if resize_to:
        img = img.resize(resize_to, Image.Resampling.LANCZOS)
    
    # Save to buffer
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=quality)
    buffer.seek(0)
    
    # Generate new filename
    original_name = image_file.name
    if '.' in original_name:
        name_parts = original_name.rsplit('.', 1)
        new_name = f"{name_parts[0]}_processed.jpg"
    else:
        new_name = f"{original_name}_processed.jpg"
    
    return ContentFile(buffer.getvalue(), name=new_name)

def process_product_image(image_file, crop_data=None):
    validate_product_image(image_file)
    return process_image(
        image_file=image_file,
        crop_data=crop_data,
        resize_to=(800, 800)
    )


def process_profile_image(image_file, crop_data=None, output_size=(300, 300), quality=90):
    
    validate_profile_image(image_file)
    
    img = Image.open(image_file)
    img = img.convert("RGB")
    
    orig_width, orig_height = img.size
    
    # Apply crop if provided
    if crop_data:
        try:
            x = int(float(crop_data.get('x', 0)))
            y = int(float(crop_data.get('y', 0)))
            crop_width = int(float(crop_data.get('width', orig_width)))
            crop_height = int(float(crop_data.get('height', orig_height)))
            
            # Ensure coordinates are within bounds
            x = max(0, min(x, orig_width - 1))
            y = max(0, min(y, orig_height - 1))
            crop_width = min(crop_width, orig_width - x)
            crop_height = min(crop_height, orig_height - y)
            
            img = img.crop((x, y, x + crop_width, y + crop_height))
        except (ValueError, TypeError, AttributeError):
            pass
    
    # Resize to output size
    img = img.resize(output_size, Image.Resampling.LANCZOS)
    
    # Save to buffer
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=quality)
    buffer.seek(0)
    
    # Generate new filename with timestamp to avoid duplicates
    import time
    original_name = image_file.name
    if '.' in original_name:
        name_parts = original_name.rsplit('.', 1)
        timestamp = int(time.time())
        new_name = f"{name_parts[0]}_{timestamp}.jpg"
    else:
        timestamp = int(time.time())
        new_name = f"{original_name}_{timestamp}.jpg"
    
    return ContentFile(buffer.getvalue(), name=new_name)

# UTILITY FUNCTIONS

def get_image_dimensions(image_file):
    
    img = Image.open(image_file)
    return img.size


def convert_to_rgb(image_file):
    
    img = Image.open(image_file)
    img = img.convert("RGB")
    
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG")
    buffer.seek(0)
    
    original_name = image_file.name
    if '.' in original_name:
        name_parts = original_name.rsplit('.', 1)
        new_name = f"{name_parts[0]}_rgb.jpg"
    else:
        new_name = f"{original_name}_rgb.jpg"
    
    return ContentFile(buffer.getvalue(), name=new_name)


def save_processed_image(image_file, upload_to, crop_data=None, resize_to=None):
    
    processed = process_image(
        image_file, 
        crop_data=crop_data, 
        resize_to=resize_to
    )
    
    # Add upload_to prefix to filename
    original_name = processed.name
    processed.name = f"{upload_to}{original_name}"
    
    return processed