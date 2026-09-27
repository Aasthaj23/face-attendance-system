from calendar import monthrange
from datetime import date

from flask import Blueprint, jsonify, request

from models import Attendance, Student, Subject
from utils.security import authorized
from utils.auth import require_role, require_student_access


analytics_bp = Blueprint("analytics", __name__)


def _status_counts(records):
    counts = {"present": 0, "absent": 0, "late": 0}
    for record in records:
        if record.status in counts:
            counts[record.status] += 1
    return counts


def _percentage(present: int, total: int) -> int:
    return round(present / total * 100) if total else 0


@analytics_bp.get("/api/analytics/overview")
@require_role("ADMIN", "TEACHER")
def overview():

    today = date.today()
    records = Attendance.query.filter(Attendance.date == today).all()
    attended_student_ids = {
        record.student_id for record in records if record.status in {"present", "late"}
    }
    late_student_ids = {record.student_id for record in records if record.status == "late"}
    total_students = Student.query.count()
    present_today = len(attended_student_ids)
    return jsonify({
        "total_students": total_students,
        "present_today": present_today,
        "absent_today": max(total_students - present_today, 0),
        "late_today": len(late_student_ids),
        "overall_percentage": _percentage(present_today, total_students),
    })


@analytics_bp.get("/api/analytics/student/<int:student_id>")
@require_student_access()
def student_analytics(student_id):
    student = Student.query.session.get(Student, student_id)
    if not student:
        return jsonify({"error": "Student not found"}), 404
    records = Attendance.query.filter_by(student_id=student_id).all()
    counts = _status_counts(records)
    total = len(records)
    return jsonify({
        "student_id": student.id,
        "name": student.name,
        "roll_no": student.roll_no,
        "total_records": total,
        "present": counts["present"],
        "absent": counts["absent"],
        "late": counts["late"],
        "attendance_percentage": _percentage(counts["present"] + counts["late"], total),
    })


@analytics_bp.get("/api/analytics/subject/<int:subject_id>")
@require_role("ADMIN", "TEACHER")
def subject_analytics(subject_id):
    subject = Subject.query.session.get(Subject, subject_id)
    if not subject:
        return jsonify({"error": "Subject not found"}), 404
    records = Attendance.query.filter_by(subject_id=subject_id).all()
    counts = _status_counts(records)
    total = len(records)
    return jsonify({
        "subject_id": subject.id,
        "name": subject.name,
        "total_records": total,
        "present": counts["present"],
        "absent": counts["absent"],
        "late": counts["late"],
        "attendance_percentage": _percentage(counts["present"] + counts["late"], total),
    })


@analytics_bp.get("/api/analytics/monthly")
@require_role("ADMIN", "TEACHER")
def monthly_analytics():
    year = request.args.get("year", str(date.today().year))
    try:
        year = int(year)
        if year < 2000 or year > 2100:
            raise ValueError
    except ValueError:
        return jsonify({"error": "Year must be between 2000 and 2100"}), 400

    months = []
    for month in range(1, 13):
        start = date(year, month, 1)
        end = date(year, month, monthrange(year, month)[1])
        records = Attendance.query.filter(
            Attendance.date >= start,
            Attendance.date <= end,
        ).all()
        counts = _status_counts(records)
        total = len(records)
        months.append({
            "month": start.strftime("%Y-%m"),
            "present": counts["present"],
            "absent": counts["absent"],
            "late": counts["late"],
            "total_records": total,
            "attendance_percentage": _percentage(counts["present"] + counts["late"], total),
        })
    return jsonify({"year": year, "months": months})