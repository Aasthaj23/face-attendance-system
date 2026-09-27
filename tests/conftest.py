import base64
import io

import pytest
from PIL import Image

from app import create_app
from config import Config
from models import db
from routes import students as students_route
from services import face_service


@pytest.fixture
def app(tmp_path, monkeypatch):
    students_file = tmp_path / "students.json"
    students_file.write_text("[]", encoding="utf-8")
    known_dir = tmp_path / "Known"
    known_dir.mkdir()

    monkeypatch.setattr("models.student.STUDENTS_FILE", students_file)
    monkeypatch.setattr("config.STUDENTS_FILE", students_file)
    monkeypatch.setattr("config.KNOWN_DIR", known_dir)
    monkeypatch.setattr(students_route, "KNOWN_DIR", known_dir)
    monkeypatch.setattr(face_service, "KNOWN_DIR", known_dir)
    monkeypatch.setattr(students_route, "FACE_RECOGNITION_AVAILABLE", False)

    test_app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "JWT_SECRET_KEY": "test-secret",
        "API_KEY": Config.API_KEY,
    })
    yield test_app
    with test_app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def api_headers():
    return {"X-API-Key": Config.API_KEY}


@pytest.fixture
def photo_data():
    image = Image.new("RGB", (32, 32), color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")
