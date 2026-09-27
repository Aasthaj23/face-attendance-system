from datetime import datetime, timedelta

from config import ATTENDANCE_THRESHOLD
from models import AttendanceRecord
from utils.security import photo_token


def already_marked(roll_no: str, name: str, subject: str, today: str) -> bool:
    query = AttendanceRecord.query.filter(
        AttendanceRecord.timestamp.startswith(today),
        AttendanceRecord.subject == subject,
    )
    query = query.filter(AttendanceRecord.roll_no == roll_no) if roll_no else query.filter(
        AttendanceRecord.name == name
    )
    return query.first() is not None


def date_range_filter(query, range_type: str):
    now = datetime.now()
    if range_type == "day":
        return query.filter(AttendanceRecord.timestamp.startswith(now.strftime("%Y-%m-%d")))
    if range_type == "week":
        return query.filter(AttendanceRecord.timestamp >= (now - timedelta(days=7)).strftime("%Y-%m-%d"))
    if range_type == "month":
        return query.filter(AttendanceRecord.timestamp >= (now - timedelta(days=30)).strftime("%Y-%m-%d"))
    return query


def attendance_stats(student: dict, all_records: list) -> dict:
    roll = student["roll_no"]
    name = student["name"].lower()
    records = [
        record
        for record in all_records
        if (record.roll_no and record.roll_no == roll) or record.name.lower() == name
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