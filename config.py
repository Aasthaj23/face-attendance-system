import os
from datetime import timedelta
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
KNOWN_DIR = BASE_DIR / "Known"
STUDENTS_FILE = BASE_DIR / "students.json"
ATTENDANCE_THRESHOLD = 75
RECOGNITION_THRESHOLD = float(os.environ.get("RECOGNITION_THRESHOLD", "0.50"))
SUBJECTS = [
    "Mathematics",
    "Physics",
    "Chemistry",
    "Computer Science",
    "English",
    "Physical Education",
]


class Config:
    RECOGNITION_THRESHOLD = RECOGNITION_THRESHOLD
    JWT_SECRET_KEY = os.environ.get(
        "JWT_SECRET_KEY",
        "4cf445c9cf0a1de286c0b537e5dfcf1d8eeaff8a02380532c1e041c15127bc24",
    )
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=2)
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{BASE_DIR / 'instance' / 'attendance.db'}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    API_KEY = os.environ.get(
        "API_KEY",
        "85ba7587e257e99ac59ad97a3e6c1ebfba1a0318ced994a895d4f9f13b28ce7d",
    )
    PHOTO_SECRET = os.environ.get("PHOTO_SECRET", "photo_secret_key_changeme")


KNOWN_DIR.mkdir(exist_ok=True)
(BASE_DIR / "instance").mkdir(exist_ok=True)