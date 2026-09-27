from datetime import datetime, timedelta

from config import ATTENDANCE_THRESHOLD
from models import Attendance
from utils.security import photo_token


def already_marked(student_id: int, subject_id: int, today) -> bool:
    return Attendance.query.filter_by(
        student_id=student_id, subject_id=subject_id, date=today
    ).first() is not None


def date_range_filter(query, range_type: str):
    today = datetime.now().date()
    if range_type == "day":
        return query.filter(Attendance.date == today)
    if range_type == "week":
        return query.filter(Attendance.date >= today - timedelta(days=7))
    if range_type == "month":
        return query.filter(Attendance.date >= today - timedelta(days=30))
    return query


def attendance_stats(student: dict, all_records: list) -> dict:
    roll = student["roll_no"]
    name = student["name"].lower()
    records = [
        record for record in all_records
        if record.student and (
            record.student.roll_no == roll or record.student.name.lower() == name
        )
    ]
    total = len(records)
    present = sum(1 for record in records if record.status == "present")
    percentage = round(present / total * 100) if total else 0
    return {
        **student,
        "photo_token": photo_token(roll),
        "total_classes": total,
        "present_count": present,
        "attendance_pct": percentage,
        "below_threshold": total > 0 and percentage < ATTENDANCE_THRESHOLD,
    }