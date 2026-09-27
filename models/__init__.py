from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()

from .student import Student
from .subject import Subject
from .attendance import Attendance
from .user import User
from .face_embedding import FaceEmbedding

AttendanceRecord = Attendance

__all__ = ["db", "Student", "Subject", "Attendance", "AttendanceRecord", "User", "FaceEmbedding"]