import numpy as np
from flask import Blueprint, jsonify, request

from config import KNOWN_DIR
from models import FaceEmbedding, Student, db
from services.face_service import (
    FACE_RECOGNITION_AVAILABLE,
    face_recognition,
    has_face,
    known_names,
    load_known_embeddings,
    recognize_face,
    serialize_embedding,
)
from services.liveness_service import LIVENESS_CHALLENGE, LivenessSessionStore
from utils.security import authorized, photo_token
from utils.logger import get_logger
from utils.validation import ValidationError, validate_name, validate_photo, validate_roll_no


recognition_bp = Blueprint("recognition", __name__)
logger = get_logger(__name__)
liveness_sessions = LivenessSessionStore()


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
    valid_embeddings = []
    for photo_data in photos:
        try:
            image = validate_photo(photo_data, has_face if FACE_RECOGNITION_AVAILABLE else None)
            if not FACE_RECOGNITION_AVAILABLE:
                continue
            image_array = np.array(image, dtype=np.uint8)
            encodings = face_recognition.face_encodings(image_array)
            if not encodings:
                continue
            valid_embeddings.append(encodings[0])
            if saved_filename is None:
                saved_filename = f"{name}_{roll_no}.jpg"
                image.save(KNOWN_DIR / saved_filename, "JPEG", quality=95)
        except ValidationError as error:
            logger.warning("Photo rejected during face registration: %s", error)
        except Exception as error:
            logger.error("Face encoding failed during registration: %s", error)
    if not saved_filename or not valid_embeddings:
        return jsonify({"error": "No usable face found in any photo - try better lighting"}), 400

    student = Student(name=name, roll_no=roll_no, photo_path=saved_filename)
    student.face_embeddings = [FaceEmbedding(embedding=serialize_embedding(embedding)) for embedding in valid_embeddings]
    db.session.add(student)
    db.session.commit()
    load_known_embeddings(FaceEmbedding.query.all())
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
        image = validate_photo(data.get("photo"))
    except ValidationError as error:
        return jsonify({"error": str(error)}), 400
    image_array = np.array(image, dtype=np.uint8)
    locations = face_recognition.face_locations(image_array)
    landmarks = face_recognition.face_landmarks(image_array, locations)
    if len(locations) != 1 or len(landmarks) != 1:
        return jsonify({"student": None, "distance": None, "error": "Exactly one face is required"}), 400
    top, right, bottom, left = locations[0]
    centroid = ((left + right) / 2.0, (top + bottom) / 2.0)
    session_id = data.get("session_id") or liveness_sessions.start()
    if not liveness_sessions.update(session_id, centroid, landmarks[0]):
        return jsonify({
            "status": "liveness_required",
            "challenge": LIVENESS_CHALLENGE,
            "session_id": session_id,
            "student": None,
        }), 202

    encodings = face_recognition.face_encodings(image_array, locations)
    if len(encodings) != 1:
        return jsonify({"student": None, "distance": None, "error": "Face encoding failed"}), 400
    identifier, distance = recognize_face(encodings[0])
    if isinstance(identifier, int):
        student = db.session.get(Student, identifier)
    else:
        student = Student.query.filter(
            db.func.lower(Student.name) == identifier.lower()
        ).first() if identifier else None
    return jsonify({
        "student_id": student.id if student else None,
        "student": {
            "id": student.id,
            "name": student.name,
            "roll_no": student.roll_no,
        } if student else None,
        "name": student.name if student else None,
        "distance": distance,
    })


@recognition_bp.post("/api/reload_faces")
def api_reload_faces():
    if not authorized():
        return jsonify({"error": "Unauthorized"}), 401
    load_known_embeddings(FaceEmbedding.query.all())
    return jsonify({"message": "Reloaded", "known": len(known_names)})