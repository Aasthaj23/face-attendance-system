from datetime import datetime, time, timedelta

from config import ATTENDANCE_SCHEDULE, ATTENDANCE_THRESHOLD
from models import Attendance, Student
from utils.security import photo_token


def determine_status(timestamp: datetime, schedule: dict | None = None) -> str:
    """Return present until the schedule grace window closes, then late."""
    schedule = schedule or ATTENDANCE_SCHEDULE
    start_value = schedule.get("start_time", "09:00:00")
    if isinstance(start_value, time):
        start_time = start_value
    else:
        start_time = datetime.strptime(str(start_value), "%H:%M:%S").time()
    late_after = int(schedule.get("late_after_minutes", 15))
    cutoff = datetime.combine(timestamp.date(), start_time) + timedelta(minutes=late_after)
    return "present" if timestamp <= cutoff else "late"


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


def attendance_stats(student: Student, all_records: list) -> dict:
    roll = student.roll_no
    name = student.name.lower()
    records = [
        record for record in all_records
        if record.student and (
            record.student.roll_no == roll or record.student.name.lower() == name
        )
    ]
    total = len(records)
    present = sum(1 for record in records if record.status in {"present", "late"})
    percentage = round(present / total * 100) if total else 0
    return {
        "id": student.id,
        "name": student.name,
        "roll_no": student.roll_no,
        "class_name": student.class_name,
        "section": student.section,
        "photo_path": student.photo_path,
        "added_on": student.created_at.isoformat() if student.created_at else None,
        "photo_token": photo_token(roll),
        "total_classes": total,
        "present_count": present,
        "attendance_pct": percentage,
        "below_threshold": total > 0 and percentage < ATTENDANCE_THRESHOLD,
    }