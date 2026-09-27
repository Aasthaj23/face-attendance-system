from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app import app
from models import Attendance, Student, Subject, db


def test_attendance_unique_student_subject_date():
    with app.app_context():
        student = Student(name="Constraint Test", roll_no="constraint-test")
        subject = Subject(name="Constraint Test Subject")
        db.session.add_all([student, subject])
        db.session.flush()

        timestamp = datetime(2026, 9, 27, 9, 0, 0)
        db.session.add(Attendance(
            student_id=student.id,
            subject_id=subject.id,
            date=timestamp.date(),
            timestamp=timestamp,
            status="present",
        ))
        db.session.commit()

        db.session.add(Attendance(
            student_id=student.id,
            subject_id=subject.id,
            date=timestamp.date(),
            timestamp=timestamp,
            status="present",
        ))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()
        db.session.delete(student)
        db.session.delete(subject)
        db.session.commit()