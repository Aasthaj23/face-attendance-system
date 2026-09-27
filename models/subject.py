from config import SUBJECTS
from . import db


class Subject(db.Model):
	__tablename__ = "subject"

	id = db.Column(db.Integer, primary_key=True)
	name = db.Column(db.String(100), nullable=False, unique=True)
	attendance_records = db.relationship("Attendance", back_populates="subject")


__all__ = ["SUBJECTS"]