import numpy as np
from flask import Blueprint, jsonify, request

from models import FaceEmbedding, Student, db
from services.face_service import (
    FACE_RECOGNITION_AVAILABLE,
    face_recognition,
    known_names,
    load_known_embeddings,
    recognize_face,
)
from services.liveness_service import LIVENESS_CHALLENGE, LivenessSessionStore
from utils.security import authorized, photo_token
from utils.auth import require_role
from utils.logger import get_logger
from utils.validation import ValidationError, validate_photo
from services.student_service import register_student


recognition_bp = Blueprint("recognition", __name__)
logger = get_logger(__name__)
liveness_sessions = LivenessSessionStore()


@recognition_bp.post("/api/recognition/register")
@recognition_bp.post("/api/register_face")
@require_role("ADMIN", "TEACHER")
def register_face():
    data = request.get_json() or {}
    name = data.get("name")
    roll_no = data.get("roll_no")
    photos = data.get("photos", [])
    try:
        student = register_student(name, roll_no, photos)
    except ValidationError as error:
        return jsonify({"error": str(error)}), 400
    load_known_embeddings(FaceEmbedding.query.all())
    return jsonify({"message": f"{student.name} registered successfully", "roll_no": student.roll_no, "filename": student.photo_path, "photo_token": photo_token(student.roll_no), "known_count": len(known_names)})


@recognition_bp.post("/api/recognition/identify")
@require_role("ADMIN", "TEACHER")
def identify_face():
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
    student_id, distance = recognize_face(encodings[0])
    student = db.session.get(Student, student_id) if student_id is not None else None
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
@require_role("ADMIN")
def api_reload_faces():
    load_known_embeddings(FaceEmbedding.query.all())
    return jsonify({"message": "Reloaded", "known": len(known_names)})