import os
import uuid
from pathlib import Path

from django.core.exceptions import ValidationError


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
PDF_EXTENSIONS = {".pdf"}
HOMEWORK_EXTENSIONS = IMAGE_EXTENSIONS | PDF_EXTENSIONS

IMAGE_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
}
PDF_CONTENT_TYPES = {"application/pdf"}
HOMEWORK_CONTENT_TYPES = IMAGE_CONTENT_TYPES | PDF_CONTENT_TYPES

MAX_PROFILE_PHOTO_SIZE_BYTES = 5 * 1024 * 1024
MAX_HOMEWORK_FILE_SIZE_BYTES = 10 * 1024 * 1024


def _file_extension(filename):
    return Path(filename or "").suffix.lower()


def _secure_name(filename):
    extension = _file_extension(filename)
    return f"{uuid.uuid4().hex}{extension}"


def profile_photo_upload_to(instance, filename):
    return os.path.join("profile_photos", _secure_name(filename))


def homework_upload_to(instance, filename):
    return os.path.join("homework", str(instance.enrollment_id or "unassigned"), _secure_name(filename))


def _validate_extension(file_obj, allowed_extensions):
    extension = _file_extension(getattr(file_obj, "name", ""))
    if extension not in allowed_extensions:
        allowed_text = ", ".join(sorted(allowed_extensions))
        raise ValidationError(f"Unsupported file extension. Allowed: {allowed_text}")


def _validate_content_type(file_obj, allowed_content_types):
    content_type = getattr(file_obj, "content_type", "")
    if content_type and content_type not in allowed_content_types:
        raise ValidationError("Unsupported file type.")


def _validate_size(file_obj, max_size):
    file_size = getattr(file_obj, "size", 0)
    if file_size and file_size > max_size:
        max_mb = max_size / (1024 * 1024)
        raise ValidationError(f"File exceeds maximum size of {max_mb:.0f} MB.")


def validate_profile_photo(file_obj):
    _validate_extension(file_obj, IMAGE_EXTENSIONS)
    _validate_content_type(file_obj, IMAGE_CONTENT_TYPES)
    _validate_size(file_obj, MAX_PROFILE_PHOTO_SIZE_BYTES)


def validate_homework_attachment(file_obj):
    _validate_extension(file_obj, HOMEWORK_EXTENSIONS)
    _validate_content_type(file_obj, HOMEWORK_CONTENT_TYPES)
    _validate_size(file_obj, MAX_HOMEWORK_FILE_SIZE_BYTES)
