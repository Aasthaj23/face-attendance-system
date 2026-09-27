from flask import Blueprint, abort, jsonify, request, send_from_directory

from config import KNOWN_DIR, SUBJECTS
from models import Attendance, FaceEmbedding, Student, db
from services.attendance_service import attendance_stats
from services.face_service import load_known_embeddings
from services.student_service import delete_student as delete_student_record
from services.student_service import register_student
from utils.security import authorized, photo_token
from utils.auth import require_role, require_student_access
from utils.validation import ValidationError


students_bp = Blueprint("students", __name__)


@students_bp.get("/api/photo/<roll_no>")
def get_photo(roll_no):
    if request.args.get("t", "") != photo_token(roll_no):
        abort(403)
    student = Student.query.filter_by(roll_no=roll_no).first()
    if student and student.photo_path and (KNOWN_DIR / student.photo_path).exists():
        response = send_from_directory(KNOWN_DIR, student.photo_path)
        response.headers["Cache-Control"] = "public, max-age=3600"
        return response
    abort(404)


@students_bp.get("/api/subjects")
@require_role("ADMIN", "TEACHER")
def get_subjects():
    return jsonify(SUBJECTS)


@students_bp.route("/api/students", methods=["GET", "POST"])
@require_role("ADMIN", "TEACHER")
def handle_students():
    if request.method == "POST":
        data = request.get_json() or {}
        try:
            student = register_student(data.get("name"), data.get("roll_no"), [data.get("photo", "")])
            load_known_embeddings(FaceEmbedding.query.all())
            return jsonify({"message": "Student registered successfully"})
        except ValidationError as error:
            return jsonify({"error": str(error)}), 400
        except Exception as error:
            return jsonify({"error": str(error)}), 500

    records = Attendance.query.all()
    return jsonify([attendance_stats(student, records) for student in Student.query.order_by(Student.id).all()])


@students_bp.get("/api/students/<int:student_id>")
@require_student_access()
def get_student_by_id(student_id):
    student = db.session.get(Student, student_id)
    if not student:
        return jsonify({"error": "Student not found"}), 404
    return jsonify({
        "id": student.id,
        "name": student.name,
        "roll_no": student.roll_no,
        "class_name": student.class_name,
        "section": student.section,
        "photo_path": student.photo_path,
        "created_at": student.created_at.isoformat() if student.created_at else None,
        "photo_token": photo_token(student.roll_no),
    })


@students_bp.delete("/api/students/<roll_no>")
@require_role("ADMIN")
def delete_student(roll_no):
    student = Student.query.filter_by(roll_no=roll_no).first()
    if not student:
        return jsonify({"error": "Student not found"}), 404
    delete_student_record(student)
    load_known_embeddings(FaceEmbedding.query.all())
    return jsonify({"message": f"Deleted {student.name}"})


@students_bp.delete("/api/students/<int:student_id>")
@require_role("ADMIN")
def delete_student_by_id(student_id):
    student = db.session.get(Student, student_id)
    if not student:
        return jsonify({"error": "Student not found"}), 404
    delete_student_record(student)
    load_known_embeddings(FaceEmbedding.query.all())
    return jsonify({"message": f"Deleted {student.name}"})