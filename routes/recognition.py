import numpy as np
from flask import Blueprint, jsonify, request

from config import KNOWN_DIR
from models import Student, db
from services.face_service import (
    FACE_RECOGNITION_AVAILABLE,
    face_recognition,
    has_face,
    known_names,
    load_known_faces,
    recognize_face,
)
from utils.security import authorized, photo_token
from utils.logger import get_logger
from utils.validation import ValidationError, validate_name, validate_photo, validate_roll_no


recognition_bp = Blueprint("recognition", __name__)
logger = get_logger(__name__)


@recognition_bp.post("/api/recognition/register")
@recognition_bp.post("/api/register_face")
def register_face():
    if not authorized():
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json() or {}
    try:
        name = validate_name(data.get("name"))
        roll_no = validate_roll_no(data.get("roll_no"))
    except ValidationError as error:
        return jsonify({"error": str(error)}), 400
    photos = data.get("photos", [])
    if not name or not roll_no:
        return jsonify({"error": "Name and roll number are required"}), 400
    if not photos:
        return jsonify({"error": "At least one photo is required"}), 400
    if Student.query.filter_by(roll_no=roll_no).first():
        return jsonify({"error": f"Roll number {roll_no} already registered"}), 409

    saved_filename = None
    for photo_data in photos:
        try:
            image = validate_photo(photo_data, has_face if FACE_RECOGNITION_AVAILABLE else None)
            saved_filename = f"{name}_{roll_no}.jpg"
            image.save(KNOWN_DIR / saved_filename, "JPEG", quality=95)
            break
        except ValidationError as error:
            logger.warning("Photo rejected during face registration: %s", error)
        except Exception as error:
            logger.error("Face encoding failed during registration: %s", error)
    if not saved_filename:
        return jsonify({"error": "No usable face found in any photo - try better lighting"}), 400

    db.session.add(Student(name=name, roll_no=roll_no, photo_path=saved_filename))
    db.session.commit()
    load_known_faces()
    logger.info("Student registered: %s (%s)", name, roll_no)
    return jsonify({"message": f"{name} registered successfully", "roll_no": roll_no, "filename": saved_filename, "photo_token": photo_token(roll_no), "known_count": len(known_names)})


@recognition_bp.post("/api/recognition/identify")
def identify_face():
    if not authorized():
        return jsonify({"error": "Unauthorized"}), 401
    if not FACE_RECOGNITION_AVAILABLE:
        return jsonify({"error": "Face recognition is unavailable"}), 503
    data = request.get_json() or {}
    try:
        image = validate_photo(data.get("photo"), has_face)
    except ValidationError as error:
        return jsonify({"error": str(error)}), 400
    image_array = np.array(image, dtype=np.uint8)
    locations = face_recognition.face_locations(image_array)
    encodings = face_recognition.face_encodings(image_array, locations)
    if len(encodings) != 1:
        return jsonify({"student": None, "distance": None, "error": "Exactly one face is required"}), 400
    name, distance = recognize_face(encodings[0])
    student = Student.query.filter(db.func.lower(Student.name) == name.lower()).first() if name else None
    return jsonify({
        "student": {
            "id": student.id,
            "name": student.name,
            "roll_no": student.roll_no,
        } if student else None,
        "name": name,
        "distance": distance,
    })


@recognition_bp.post("/api/reload_faces")
def api_reload_faces():
    if not authorized():
        return jsonify({"error": "Unauthorized"}), 401
    load_known_faces()
    return jsonify({"message": "Reloaded", "known": len(known_names)})