from . import db


class FaceEmbedding(db.Model):
    __tablename__ = "face_embedding"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(
        db.Integer,
        db.ForeignKey("student.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    embedding = db.Column(db.LargeBinary, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    student = db.relationship("Student", back_populates="face_embeddings")