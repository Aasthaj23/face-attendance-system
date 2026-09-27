import json

from config import STUDENTS_FILE
from . import db


class Student(db.Model):
    __tablename__ = "student"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    roll_no = db.Column(db.String(50), nullable=False, unique=True, index=True)
    class_name = db.Column(db.String(100), nullable=True)
    section = db.Column(db.String(20), nullable=True)
    photo_path = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    attendance_records = db.relationship(
        "Attendance", back_populates="student", cascade="all, delete-orphan"
    )


def load_students() -> list:
    try:
        with STUDENTS_FILE.open(encoding="utf-8") as students_file:
            return json.load(students_file)
    except (OSError, ValueError):
        return []


def save_students(students: list) -> None:
    with STUDENTS_FILE.open("w", encoding="utf-8") as students_file:
        json.dump(students, students_file, indent=2)


def find_student(students: list, *, roll_no: str = "", name: str = "") -> dict | None:
    if roll_no:
        match = next((student for student in students if student.get("roll_no") == roll_no), None)
        if match:
            return match
    if name:
        normalized_name = name.lower()
        return next(
            (student for student in students if student.get("name", "").lower() == normalized_name),
            None,
        )
    return None