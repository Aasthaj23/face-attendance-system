import os

import numpy as np
from PIL import Image

from config import KNOWN_DIR, RECOGNITION_THRESHOLD
from utils.logger import get_logger

try:
    import face_recognition
except ImportError:
    face_recognition = None


FACE_RECOGNITION_AVAILABLE = face_recognition is not None
known_encodings: list = []
known_names: list = []
known_student_ids: list = []
logger = get_logger(__name__)


def serialize_embedding(embedding) -> bytes:
    return np.asarray(embedding, dtype=np.float64).tobytes()


def deserialize_embedding(value: bytes):
    return np.frombuffer(value, dtype=np.float64).copy()


def load_known_embeddings(records) -> None:
    if not records:
        load_known_faces()
        return
    known_encodings.clear()
    known_names.clear()
    known_student_ids.clear()
    for record in records:
        if record.student and record.embedding:
            known_encodings.append(deserialize_embedding(record.embedding))
            known_names.append(record.student.name)
            known_student_ids.append(record.student_id)
    logger.info("Loaded %d database face embeddings", len(known_names))


def load_known_faces() -> None:
    known_encodings.clear()
    known_names.clear()
    known_student_ids.clear()
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
                known_student_ids.append(None)
        except Exception as error:
            logger.error("Face encoding failed for %s: %s", filename, error)
    logger.info("Loaded %d known faces", len(known_names))


def has_face(image: Image.Image) -> bool:
    if not FACE_RECOGNITION_AVAILABLE:
        return False
    try:
        return bool(face_recognition.face_encodings(np.array(image, dtype=np.uint8)))
    except (TypeError, ValueError):
        return False


def recognize_face(face_encoding):
    """Return the owning student_id and distance, or an unknown result."""
    if not FACE_RECOGNITION_AVAILABLE or not known_encodings:
        return None, float("inf")

    try:
        distances = face_recognition.face_distance(known_encodings, face_encoding)
        best_index = int(np.argmin(distances))
        best_distance = float(distances[best_index])
    except (TypeError, ValueError):
        return None, float("inf")

    if best_distance <= RECOGNITION_THRESHOLD:
        student_id = known_student_ids[best_index] if best_index < len(known_student_ids) else None
        if student_id is None:
            logger.warning("Matched face has no database student_id")
            return None, best_distance
        logger.info("Face recognized: student_id=%s (distance=%.4f)", student_id, best_distance)
        return student_id, best_distance

    logger.warning("Unknown face (distance=%.4f)", best_distance)
    return None, best_distance


load_known_faces()