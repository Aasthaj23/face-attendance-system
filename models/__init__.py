from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()

from .student import Student
from .subject import Subject
from .attendance import Attendance

AttendanceRecord = Attendance

__all__ = ["db", "Student", "Subject", "Attendance", "AttendanceRecord"]