import os
from datetime import datetime

from flask import Blueprint, abort, jsonify, request, send_from_directory

from config import KNOWN_DIR, SUBJECTS
from models import AttendanceRecord
from models.student import find_student, load_students, save_students
from services.attendance_service import attendance_stats
from services.face_service import FACE_RECOGNITION_AVAILABLE, has_face, load_known_faces
from utils.security import authorized, photo_token
from utils.validation import decode_photo


students_bp = Blueprint("students", __name__)


@students_bp.get("/api/photo/<roll_no>")
def get_photo(roll_no):
    if request.args.get("t", "") != photo_token(roll_no):
        abort(403)
    student = find_student(load_students(), roll_no=roll_no)
    if student and (KNOWN_DIR / student["filename"]).exists():
        response = send_from_directory(KNOWN_DIR, student["filename"])
        response.headers["Cache-Control"] = "public, max-age=3600"
        return response
    abort(404)


@students_bp.get("/api/subjects")
def get_subjects():
    if not authorized():
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(SUBJECTS)


@students_bp.route("/api/students", methods=["GET", "POST"])
def handle_students():
    if not authorized():
        return jsonify({"error": "Unauthorized"}), 401
    if request.method == "POST":
        data = request.get_json() or {}
        name = (data.get("name") or "").strip()
        roll = (data.get("roll_no") or "").strip()
        photo = data.get("photo", "")
        if not name or not roll or not photo:
            return jsonify({"error": "Name, roll number and photo are all required"}), 400
        students = load_students()
        if find_student(students, roll_no=roll):
            return jsonify({"error": f"Roll number {roll} already exists"}), 409
        try:
            image = decode_photo(photo)
            if FACE_RECOGNITION_AVAILABLE and not has_face(image):
                return jsonify({"error": "No face detected - use a clear front-facing photo"}), 400
            filename = f"{name}_{roll}.jpg"
            image.save(KNOWN_DIR / filename, "JPEG", quality=95)
            students.append({"name": name, "roll_no": roll, "filename": filename, "added_on": datetime.now().isoformat()})
            save_students(students)
            load_known_faces()
            return jsonify({"message": "Student registered successfully"})
        except Exception as error:
            return jsonify({"error": str(error)}), 500

    records = AttendanceRecord.query.all()
    return jsonify([attendance_stats(student, records) for student in load_students()])


@students_bp.delete("/api/students/<roll_no>")
def delete_student(roll_no):
    if not authorized():
        return jsonify({"error": "Unauthorized"}), 401
    students = load_students()
    student = find_student(students, roll_no=roll_no)
    if not student:
        return jsonify({"error": "Student not found"}), 404
    photo_path = KNOWN_DIR / student["filename"]
    if photo_path.exists():
        photo_path.unlink()
    save_students([item for item in students if item["roll_no"] != roll_no])
    load_known_faces()
    return jsonify({"message": f"Deleted {student['name']}"})