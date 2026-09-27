import base64
import io

import pytest
from PIL import Image

from utils.validation import (
    ValidationError,
    validate_date,
    validate_photo,
    validate_status,
    validate_time,
)


def encoded_image(image_format):
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), "white").save(buffer, format=image_format)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def test_status_rejects_unknown_value():
    with pytest.raises(ValidationError):
        validate_status("hello")


def test_date_and_time_require_expected_formats():
    with pytest.raises(ValidationError):
        validate_date("27/09/2026")
    with pytest.raises(ValidationError):
        validate_time("9:30")


def test_jpeg_and_png_are_accepted():
    assert validate_photo(encoded_image("JPEG")).mode == "RGB"
    assert validate_photo(encoded_image("PNG")).mode == "RGB"


def test_invalid_image_is_rejected():
    with pytest.raises(ValidationError):
        validate_photo(base64.b64encode(b"not an image").decode("ascii"))


def test_face_checker_can_reject_image():
    with pytest.raises(ValidationError):
        validate_photo(encoded_image("JPEG"), face_checker=lambda image: False)