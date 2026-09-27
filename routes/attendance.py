from datetime import datetime

from flask import Blueprint, jsonify, request

from models import AttendanceRecord, db
from models.student import find_student, load_students
from services.attendance_service import already_marked, date_range_filter
from utils.security import authorized, photo_token


attendance_bp = Blueprint("attendance", __name__)


@attendance_bp.get("/api/full_records")
def full_records():
    if not authorized():
        return jsonify({"error": "Unauthorized"}), 401
    query = date_range_filter(AttendanceRecord.query, request.args.get("range", "all"))
    subject = request.args.get("subject", "")
    if subject and subject != "all":
        query = query.filter(AttendanceRecord.subject == subject)
    students = load_students()
    records = []
    for record in query.order_by(AttendanceRecord.id.desc()).all():
        student = find_student(students, roll_no=record.roll_no or "", name=record.name)
        records.append({
            "id": record.id,
            "name": record.name,
            "roll_no": record.roll_no or "",
            "photo_token": photo_token(student["roll_no"]) if student else "",
            "subject": record.subject or "General",
            "date": record.timestamp.split(" ")[0],
            "time": record.timestamp.split(" ")[1] if " " in record.timestamp else "",
            "status": record.status,
        })
    return jsonify(records)


@attendance_bp.post("/api/records/<int:record_id>/toggle")
def toggle_record(record_id):
    if not authorized():
        return jsonify({"error": "Unauthorized"}), 401
    record = db.session.get(AttendanceRecord, record_id)
    if not record:
        return jsonify({"error": "Record not found"}), 404
    record.status = "absent" if record.status == "present" else "present"
    db.session.commit()
    return jsonify({"id": record.id, "status": record.status})


@attendance_bp.post("/api/records")
def add_record():
    if not authorized():
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Name is required"}), 400
    now = datetime.now()
    record = AttendanceRecord(
        name=name,
        roll_no=data.get("roll_no", ""),
        subject=data.get("subject", "General"),
        timestamp=f"{data.get('date', now.strftime('%Y-%m-%d'))} {data.get('time', now.strftime('%H:%M:%S'))}",
        status=data.get("status", "present"),
    )
    db.session.add(record)
    db.session.commit()
    return jsonify({"message": "Record added", "id": record.id})


@attendance_bp.post("/api/detect")
def api_detect():
    if not authorized():
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    subject = data.get("subject", "General")
    if not name:
        return jsonify({"error": "Name required"}), 400
    today = datetime.now().strftime("%Y-%m-%d")
    student = find_student(load_students(), name=name)
    roll_no = student["roll_no"] if student else ""
    if already_marked(roll_no, name, subject, today):
        return jsonify({"status": "duplicate", "message": f"{name} already marked for {subject} today"})
    record = AttendanceRecord(name=student["name"] if student else name, roll_no=roll_no, subject=subject, timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), status="present")
    db.session.add(record)
    db.session.commit()
    return jsonify({"status": "present", "name": name, "roll_no": roll_no, "id": record.id})


@attendance_bp.post("/api/mark_absent")
def mark_absent():
    if not authorized():
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json() or {}
    subject = data.get("subject", "General")
    present_names = {name.lower() for name in data.get("present_names", [])}
    today = datetime.now().strftime("%Y-%m-%d")
    marked_absent = []
    for student in load_students():
        if student["name"].lower() in present_names or already_marked(student["roll_no"], student["name"], subject, today):
            continue
        db.session.add(AttendanceRecord(name=student["name"], roll_no=student["roll_no"], subject=subject, timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), status="absent"))
        marked_absent.append(student["name"])
    db.session.commit()
    return jsonify({"marked_absent": marked_absent, "count": len(marked_absent)})