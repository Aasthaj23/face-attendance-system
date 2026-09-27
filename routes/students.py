from flask import Blueprint, abort, jsonify, request, send_from_directory

from config import KNOWN_DIR, SUBJECTS
from models import Attendance, FaceEmbedding, Student, db
from services.attendance_service import attendance_stats
from services.face_service import FACE_RECOGNITION_AVAILABLE, has_face, load_known_embeddings
from utils.security import authorized, photo_token
from utils.logger import get_logger
from utils.validation import ValidationError, validate_name, validate_photo, validate_roll_no


students_bp = Blueprint("students", __name__)
logger = get_logger(__name__)


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
        try:
            name = validate_name(data.get("name"))
            roll = validate_roll_no(data.get("roll_no"))
        except ValidationError as error:
            return jsonify({"error": str(error)}), 400
        photo = data.get("photo", "")
        if Student.query.filter_by(roll_no=roll).first():
            return jsonify({"error": f"Roll number {roll} already exists"}), 400
        try:
            image = validate_photo(photo, has_face if FACE_RECOGNITION_AVAILABLE else None)
            filename = f"{name}_{roll}.jpg"
            image.save(KNOWN_DIR / filename, "JPEG", quality=95)
            student = Student(name=name, roll_no=roll, photo_path=filename)
            db.session.add(student)
            db.session.commit()
            load_known_embeddings(FaceEmbedding.query.all())
            logger.info("Student registered: %s (%s)", name, roll)
            return jsonify({"message": "Student registered successfully"})
        except ValidationError as error:
            return jsonify({"error": str(error)}), 400
        except Exception as error:
            return jsonify({"error": str(error)}), 500

    records = Attendance.query.all()
    return jsonify([attendance_stats(student, records) for student in Student.query.order_by(Student.id).all()])


@students_bp.get("/api/students/<int:student_id>")
def get_student_by_id(student_id):
    if not authorized():
        return jsonify({"error": "Unauthorized"}), 401
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
def delete_student(roll_no):
    if not authorized():
        return jsonify({"error": "Unauthorized"}), 401
    student = Student.query.filter_by(roll_no=roll_no).first()
    if not student:
        return jsonify({"error": "Student not found"}), 404
    photo_path = KNOWN_DIR / (student.photo_path or "")
    if photo_path.exists():
        photo_path.unlink()
    db.session.delete(student)
    db.session.commit()
    load_known_embeddings(FaceEmbedding.query.all())
    return jsonify({"message": f"Deleted {student.name}"})


@students_bp.delete("/api/students/<int:student_id>")
def delete_student_by_id(student_id):
    if not authorized():
        return jsonify({"error": "Unauthorized"}), 401
    student = db.session.get(Student, student_id)
    if not student:
        return jsonify({"error": "Student not found"}), 404
    photo_path = KNOWN_DIR / (student.photo_path or "")
    if photo_path.exists():
        photo_path.unlink()
    db.session.delete(student)
    db.session.commit()
    load_known_embeddings(FaceEmbedding.query.all())
    return jsonify({"message": f"Deleted {student.name}"})