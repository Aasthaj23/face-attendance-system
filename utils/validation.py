import base64
import binascii
import io
import re
from datetime import datetime

from PIL import Image, UnidentifiedImageError


MAX_PHOTO_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG"}
VALID_STATUSES = {"present", "absent", "late"}
_NAME_PATTERN = re.compile(r"^[\w .'-]{1,100}$", re.UNICODE)
_ROLL_PATTERN = re.compile(r"^[\w-]{1,50}$", re.UNICODE)


class ValidationError(ValueError):
    pass


def validate_name(value: str) -> str:
    value = (value or "").strip()
    if not value or not _NAME_PATTERN.fullmatch(value):
        raise ValidationError("Name is required and may contain only letters, spaces, and punctuation")
    return value


def validate_roll_no(value: str) -> str:
    value = (value or "").strip()
    if not value or not _ROLL_PATTERN.fullmatch(value):
        raise ValidationError("Roll number is required and may contain only letters, numbers, underscores, and hyphens")
    return value


def validate_subject(value: str) -> str:
    value = (value or "").strip()
    if not value or len(value) > 100:
        raise ValidationError("Subject is required")
    return value


def validate_status(value: str, default: str = "present") -> str:
    value = (value or default).strip().lower()
    if value not in VALID_STATUSES:
        raise ValidationError("Status must be one of: present, absent, late")
    return value


def validate_date(value: str) -> str:
    value = (value or "").strip()
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except (TypeError, ValueError):
        raise ValidationError("Date must use YYYY-MM-DD format") from None
    return value


def validate_time(value: str) -> str:
    value = (value or "").strip()
    try:
        datetime.strptime(value, "%H:%M:%S")
    except (TypeError, ValueError):
        raise ValidationError("Time must use HH:MM:SS format") from None
    return value


def _decode_photo_bytes(photo_data: str) -> bytes:
    if not isinstance(photo_data, str) or not photo_data.strip():
        raise ValidationError("Photo is required")
    encoded = photo_data.split(",", 1)[-1]
    try:
        decoded = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise ValidationError("Photo must be valid base64 image data") from None
    if len(decoded) > MAX_PHOTO_BYTES:
        raise ValidationError("Photo exceeds the 5 MB size limit")
    return decoded


def validate_photo(photo_data: str, face_checker=None) -> Image.Image:
    decoded = _decode_photo_bytes(photo_data)
    try:
        image = Image.open(io.BytesIO(decoded))
        image.verify()
        image = Image.open(io.BytesIO(decoded))
        image_format = image.format
        image = image.convert("RGB")
    except (UnidentifiedImageError, OSError, SyntaxError):
        raise ValidationError("Photo must be a valid JPEG or PNG image") from None

    if image_format not in ALLOWED_IMAGE_FORMATS:
        raise ValidationError("Photo must be a JPEG or PNG image")
    if face_checker is not None and not face_checker(image):
        raise ValidationError("Photo must contain a detectable face")
    return image


def decode_photo(photo_data: str) -> Image.Image:
    return validate_photo(photo_data)