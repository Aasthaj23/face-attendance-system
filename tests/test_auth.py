from app import app


def test_login_returns_token():
    response = app.test_client().post("/api/login", json={"username": "admin", "password": "1234"})
    assert response.status_code == 200
    assert response.json["token"]


def test_login_rejects_invalid_credentials():
    response = app.test_client().post("/api/login", json={"username": "admin", "password": "wrong"})
    assert response.status_code == 401