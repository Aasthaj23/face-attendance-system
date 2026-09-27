import base64
import io

import pytest
from PIL import Image

from app import create_app
from config_testing import TestingConfig
from models import User, db
from services import face_service


@pytest.fixture
def app(tmp_path, monkeypatch):
    known_dir = tmp_path / "Known"
    known_dir.mkdir()

    monkeypatch.setattr("config.KNOWN_DIR", known_dir)
    monkeypatch.setattr(face_service, "KNOWN_DIR", known_dir)

    test_app = create_app(vars(TestingConfig))
    with test_app.app_context():
        test_user = User(username="test_admin", role="ADMIN")
        test_user.set_password("test-password")
        db.session.add(test_user)
        db.session.commit()
    yield test_app
    with test_app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def api_headers():
    return {"X-API-Key": TestingConfig.API_KEY}


@pytest.fixture
def photo_data():
    image = Image.new("RGB", (32, 32), color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")
