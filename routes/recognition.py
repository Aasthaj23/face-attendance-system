from datetime import datetime

from flask import Blueprint, jsonify, request

from config import KNOWN_DIR
from models.student import find_student, load_students, save_students
from services.face_service import FACE_RECOGNITION_AVAILABLE, has_face, known_names, load_known_faces
from utils.security import authorized, photo_token
from utils.validation import decode_photo


recognition_bp = Blueprint("recognition", __name__)


@recognition_bp.post("/api/register_face")
def register_face():
    if not authorized():
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    roll_no = (data.get("roll_no") or "").strip()
    photos = data.get("photos", [])
    if not name or not roll_no:
        return jsonify({"error": "Name and roll number are required"}), 400
    if not photos:
        return jsonify({"error": "At least one photo is required"}), 400
    students = load_students()
    if find_student(students, roll_no=roll_no):
        return jsonify({"error": f"Roll number {roll_no} already registered"}), 409

    saved_filename = None
    for photo_data in photos:
        try:
            image = decode_photo(photo_data)
            if FACE_RECOGNITION_AVAILABLE and not has_face(image):
                continue
            saved_filename = f"{name}_{roll_no}.jpg"
            image.save(KNOWN_DIR / saved_filename, "JPEG", quality=95)
            break
        except Exception as error:
            print(f"[register_face] photo error: {error}")
    if not saved_filename:
        return jsonify({"error": "No usable face found in any photo - try better lighting"}), 400

    students.append({"name": name, "roll_no": roll_no, "filename": saved_filename, "added_on": datetime.now().isoformat()})
    save_students(students)
    load_known_faces()
    return jsonify({"message": f"{name} registered successfully", "roll_no": roll_no, "filename": saved_filename, "photo_token": photo_token(roll_no), "known_count": len(known_names)})


@recognition_bp.post("/api/reload_faces")
def api_reload_faces():
    if not authorized():
        return jsonify({"error": "Unauthorized"}), 401
    load_known_faces()
    return jsonify({"message": "Reloaded", "known": len(known_names)})