import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
KNOWN_DIR = BASE_DIR / "Known"
ATTENDANCE_THRESHOLD = 75
ATTENDANCE_SCHEDULE = {
    "start_time": os.environ.get("ATTENDANCE_START_TIME", "09:00:00"),
    "late_after_minutes": int(os.environ.get("ATTENDANCE_LATE_AFTER_MINUTES", "15")),
}
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
    ATTENDANCE_SCHEDULE = ATTENDANCE_SCHEDULE
    RECOGNITION_THRESHOLD = RECOGNITION_THRESHOLD
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=2)
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        f"sqlite:///{BASE_DIR / 'instance' / 'attendance.db'}",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    API_KEY = os.environ.get("API_KEY", "")
    PHOTO_SECRET = os.environ.get("PHOTO_SECRET", "")


REQUIRED_SECRETS = ("JWT_SECRET_KEY", "API_KEY", "PHOTO_SECRET")


def validate_security_config(config) -> None:
    missing = [name for name in REQUIRED_SECRETS if not str(config.get(name, "")).strip()]
    if missing:
        raise RuntimeError(
            "Missing required security configuration: "
            + ", ".join(missing)
            + ". Set them in the environment or a local .env file."
        )
    weak = [name for name in REQUIRED_SECRETS if len(str(config[name])) < 32]
    if weak:
        raise RuntimeError(
            "Security secrets must be at least 32 characters: " + ", ".join(weak)
        )


KNOWN_DIR.mkdir(exist_ok=True)
(BASE_DIR / "instance").mkdir(exist_ok=True)