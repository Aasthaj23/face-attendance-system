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
    face_embeddings = db.relationship(
        "FaceEmbedding", back_populates="student", cascade="all, delete-orphan"
    )


