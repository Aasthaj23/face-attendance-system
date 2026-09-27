from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()

from .attendance import AttendanceRecord

__all__ = ["db", "AttendanceRecord"]