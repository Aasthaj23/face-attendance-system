import os

import numpy as np
from PIL import Image

from config import KNOWN_DIR

try:
    import face_recognition
except ImportError:
    face_recognition = None


FACE_RECOGNITION_AVAILABLE = face_recognition is not None
known_encodings: list = []
known_names: list = []


def load_known_faces() -> None:
    known_encodings.clear()
    known_names.clear()
    if not FACE_RECOGNITION_AVAILABLE:
        return

    for filename in os.listdir(KNOWN_DIR):
        if not filename.lower().endswith((".jpg", ".jpeg", ".png")):
            continue
        path = KNOWN_DIR / filename
        name = path.stem.rsplit("_", 1)[0]
        try:
            image = np.array(Image.open(path).convert("RGB"), dtype=np.uint8)
            encodings = face_recognition.face_encodings(image)
            if encodings:
                known_encodings.append(encodings[0])
                known_names.append(name)
        except Exception as error:
            print(f"[faces] Error loading {filename}: {error}")
    print(f"[faces] {len(known_names)} loaded")


def has_face(image: Image.Image) -> bool:
    return bool(
        FACE_RECOGNITION_AVAILABLE
        and face_recognition.face_encodings(np.array(image, dtype=np.uint8))
    )


load_known_faces()