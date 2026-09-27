import base64
import io

from PIL import Image


def decode_photo(photo_data: str) -> Image.Image:
    if "," in photo_data:
        photo_data = photo_data.split(",", 1)[1]
    return Image.open(io.BytesIO(base64.b64decode(photo_data))).convert("RGB")