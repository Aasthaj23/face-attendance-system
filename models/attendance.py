from . import db


class Attendance(db.Model):
    __tablename__ = "attendance"
    __table_args__ = (
        db.UniqueConstraint(
            "student_id",
            "subject_id",
            "date",
            name="uq_attendance_student_subject_date",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False, index=True)
    subject_id = db.Column(db.Integer, db.ForeignKey("subject.id"), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False, index=True)
    timestamp = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), nullable=False)
    student = db.relationship("Student", back_populates="attendance_records")
    subject = db.relationship("Subject", back_populates="attendance_records")