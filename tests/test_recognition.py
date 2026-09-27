from app import app
from config import Config


def test_reload_faces_requires_authorization():
    assert app.test_client().post("/api/reload_faces").status_code == 401


def test_reload_faces_with_api_key():
    response = app.test_client().post("/api/reload_faces", headers={"X-API-Key": Config.API_KEY})
    assert response.status_code == 200
    assert "known" in response.json