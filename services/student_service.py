import numpy as np

from config import KNOWN_DIR
from models import FaceEmbedding, Student, db
from services import face_service
from utils.logger import get_logger
from utils.validation import ValidationError, validate_name, validate_photo, validate_roll_no


logger = get_logger(__name__)


def create_face_embeddings(photos: list[str]):
    if not face_service.FACE_RECOGNITION_AVAILABLE:
        raise ValidationError("Face recognition is unavailable")

    embeddings = []
    embedding_keys = set()
    first_image = None
    for photo_data in photos:
        try:
            image = validate_photo(photo_data)
            image_array = np.array(image, dtype=np.uint8)
            encodings = face_service.face_recognition.face_encodings(image_array)
            if not encodings:
                continue
            embedding = encodings[0]
            key = face_service.serialize_embedding(embedding)
            if key in embedding_keys:
                continue
            embedding_keys.add(key)
            embeddings.append(embedding)
            if first_image is None:
                first_image = image
        except ValidationError as error:
            logger.warning("Photo rejected during student registration: %s", error)
    if not embeddings or first_image is None:
        raise ValidationError("No usable face found in any photo - try better lighting")
    return first_image, embeddings


def register_student(name: str, roll_no: str, photos: list[str]) -> Student:
    name = validate_name(name)
    roll_no = validate_roll_no(roll_no)
    if not photos:
        raise ValidationError("At least one photo is required")
    if Student.query.filter_by(roll_no=roll_no).first():
        raise ValidationError(f"Roll number {roll_no} already registered")

    display_image, embeddings = create_face_embeddings(photos)
    filename = f"{name}_{roll_no}.jpg"
    photo_path = KNOWN_DIR / filename
    try:
        display_image.save(photo_path, "JPEG", quality=95)
        student = Student(name=name, roll_no=roll_no, photo_path=filename)
        student.face_embeddings = [
            FaceEmbedding(embedding=face_service.serialize_embedding(embedding))
            for embedding in embeddings
        ]
        db.session.add(student)
        db.session.commit()
    except Exception:
        db.session.rollback()
        if photo_path.exists():
            photo_path.unlink()
        raise
    logger.info("Student registered with %d face embeddings: %s (%s)", len(embeddings), name, roll_no)
    return student


def delete_student(student: Student) -> None:
    photo_path = KNOWN_DIR / (student.photo_path or "")
    if photo_path.exists():
        photo_path.unlink()
    db.session.delete(student)
    db.session.commit()
    logger.info("Student deleted: %s (%s)", student.name, student.roll_no)
