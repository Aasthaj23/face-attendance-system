from datetime import datetime

from flask import Blueprint, jsonify, request, send_file
from sqlalchemy.exc import IntegrityError

from models import Attendance, Student, Subject, db
from services.attendance_service import already_marked, date_range_filter, determine_status
from services.export_service import attendance_csv
from utils.security import authorized, photo_token
from utils.auth import require_role
from utils.logger import get_logger
from utils.validation import (
    ValidationError,
    validate_date,
    validate_name,
    validate_roll_no,
    validate_status,
    validate_subject,
    validate_time,
)


attendance_bp = Blueprint("attendance", __name__)
logger = get_logger(__name__)


def get_subject(name: str) -> Subject:
    subject = Subject.query.filter_by(name=name).first()
    if not subject:
        subject = Subject(name=name)
        db.session.add(subject)
        db.session.flush()
    return subject


def get_student(name: str, roll_no: str = "") -> Student:
    student = Student.query.filter_by(roll_no=roll_no).first() if roll_no else None
    if not student:
        student = Student.query.filter(db.func.lower(Student.name) == name.lower()).first()
    if not student:
        student = Student(name=name, roll_no=roll_no or f"legacy-{name.lower().replace(' ', '-')}")
        db.session.add(student)
        db.session.flush()
    return student


@attendance_bp.get("/api/attendance/export")
@require_role("ADMIN", "TEACHER")
def export_attendance():
    query = date_range_filter(Attendance.query, request.args.get("range", "all"))
    subject_name = request.args.get("subject", "")
    if subject_name and subject_name != "all":
        query = query.join(Attendance.subject).filter(Subject.name == subject_name)
    records = query.order_by(Attendance.date.desc(), Attendance.timestamp.desc()).all()
    return send_file(
        attendance_csv(records),
        mimetype="text/csv",
        as_attachment=True,
        download_name="attendance.csv",
    )


@attendance_bp.get("/api/attendance")
@attendance_bp.get("/api/full_records")
@require_role("ADMIN", "TEACHER")
def full_records():
    query = date_range_filter(Attendance.query, request.args.get("range", "all"))
    subject_name = request.args.get("subject", "")
    if subject_name and subject_name != "all":
        query = query.join(Attendance.subject).filter(Subject.name == subject_name)
    records = []
    for record in query.order_by(Attendance.id.desc()).all():
        records.append({
            "id": record.id,
            "name": record.student.name,
            "roll_no": record.student.roll_no,
            "photo_token": photo_token(record.student.roll_no),
            "subject": record.subject.name,
            "date": record.date.isoformat(),
            "time": record.timestamp.strftime("%H:%M:%S"),
            "status": record.status,
        })
    return jsonify(records)


@attendance_bp.patch("/api/attendance/<int:record_id>")
@attendance_bp.post("/api/records/<int:record_id>/toggle")
@require_role("ADMIN")
def toggle_record(record_id):
    record = db.session.get(Attendance, record_id)
    if not record:
        return jsonify({"error": "Record not found"}), 404
    data = request.get_json(silent=True) or {}
    if "status" in data:
        try:
            record.status = validate_status(data["status"])
        except ValidationError as error:
            return jsonify({"error": str(error)}), 400
    else:
        record.status = "present" if record.status == "absent" else "absent"
    db.session.commit()
    return jsonify({"id": record.id, "status": record.status})


@attendance_bp.post("/api/attendance")
@attendance_bp.post("/api/records")
@require_role("ADMIN", "TEACHER")
def add_record():
    data = request.get_json() or {}
    now = datetime.now()
    try:
        name = validate_name(data.get("name"))
        roll_no = validate_roll_no(data.get("roll_no")) if data.get("roll_no") else ""
        subject_name = validate_subject(data.get("subject", "General"))
        status = validate_status(data.get("status", "present"))
        date_value = validate_date(data.get("date", now.strftime("%Y-%m-%d")))
        time_value = validate_time(data.get("time", now.strftime("%H:%M:%S")))
    except ValidationError as error:
        return jsonify({"error": str(error)}), 400
    timestamp = datetime.strptime(f"{date_value} {time_value}", "%Y-%m-%d %H:%M:%S")
    student = get_student(name, roll_no)
    subject = get_subject(subject_name)
    record = Attendance(student=student, subject=subject, date=timestamp.date(), timestamp=timestamp, status=status)
    db.session.add(record)
    db.session.commit()
    logger.info("Attendance recorded: %s, %s, %s", student.name, subject.name, status)
    return jsonify({"message": "Record added", "id": record.id})


@attendance_bp.post("/api/detect")
@require_role("ADMIN", "TEACHER")
def api_detect():
    data = request.get_json() or {}
    try:
        name = validate_name(data.get("name"))
    except ValidationError as error:
        return jsonify({"error": str(error)}), 400
    student = get_student(name)
    try:
        subject_name = validate_subject(data.get("subject", "General"))
    except ValidationError as error:
        return jsonify({"error": str(error)}), 400
    subject = get_subject(subject_name)
    today = datetime.now().date()
    if already_marked(student.id, subject.id, today):
        logger.warning("Duplicate attendance: %s, %s, %s", student.name, subject.name, today)
        return jsonify({"status": "duplicate", "message": f"{student.name} already marked for {subject.name} today"})
    timestamp = datetime.now()
    status = determine_status(timestamp)
    record = Attendance(student=student, subject=subject, date=today, timestamp=timestamp, status=status)
    db.session.add(record)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        logger.warning("Duplicate attendance: %s, %s, %s", student.name, subject.name, today)
        return jsonify({"status": "duplicate", "message": f"{student.name} already marked for {subject.name} today"})
    logger.info("Attendance recorded: %s, %s, %s", student.name, subject.name, status)
    return jsonify({"status": status, "name": student.name, "roll_no": student.roll_no, "id": record.id})


@attendance_bp.post("/api/mark_absent")
@require_role("ADMIN", "TEACHER")
def mark_absent():
    data = request.get_json() or {}
    try:
        subject_name = validate_subject(data.get("subject", "General"))
    except ValidationError as error:
        return jsonify({"error": str(error)}), 400
    subject = get_subject(subject_name)
    present_names = {name.lower() for name in data.get("present_names", [])}
    today = datetime.now().date()
    marked_absent = []
    for student in Student.query.all():
        if student.name.lower() in present_names or already_marked(student.id, subject.id, today):
            continue
        db.session.add(Attendance(student=student, subject=subject, date=today, timestamp=datetime.now(), status="absent"))
        marked_absent.append(student.name)
    db.session.commit()
    return jsonify({"marked_absent": marked_absent, "count": len(marked_absent)})