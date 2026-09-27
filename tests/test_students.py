from app import app
from config import Config


def test_students_requires_authorization():
    assert app.test_client().get("/api/students").status_code == 401


def test_students_accepts_api_key():
    response = app.test_client().get("/api/students", headers={"X-API-Key": Config.API_KEY})
    assert response.status_code == 200
    assert isinstance(response.json, list)