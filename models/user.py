from datetime import datetime

from werkzeug.security import generate_password_hash, check_password_hash

from . import db


USER_ROLES = {"ADMIN", "TEACHER", "STUDENT"}


class User(db.Model):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="STUDENT")
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    student = db.relationship("Student", backref="user_account")

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def set_role(self, role: str) -> None:
        role = role.upper()
        if role not in USER_ROLES:
            raise ValueError("Role must be ADMIN, TEACHER, or STUDENT")
        self.role = role