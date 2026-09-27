from . import db


class AttendanceRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    roll_no = db.Column(db.String(50), nullable=True, index=True)
    subject = db.Column(db.String(100), nullable=True, default="General")
    timestamp = db.Column(db.String(50), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False)