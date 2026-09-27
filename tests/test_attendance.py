from app import app


def test_attendance_requires_authorization():
    assert app.test_client().get("/api/full_records").status_code == 401


def test_status_is_public():
    response = app.test_client().get("/api/status")
    assert response.status_code == 200
    assert "subjects" in response.json