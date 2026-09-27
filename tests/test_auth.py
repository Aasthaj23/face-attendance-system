def test_correct_credentials_return_200(client):
    response = client.post("/api/login", json={"username": "test_admin", "password": "test-password"})
    assert response.status_code == 200
    assert response.json["token"]
    assert response.json["role"] == "ADMIN"


def test_wrong_credentials_return_401(client):
    response = client.post("/api/login", json={"username": "admin", "password": "wrong"})
    assert response.status_code == 401


def test_missing_token_returns_401(client):
    response = client.get("/api/students")
    assert response.status_code == 401


def test_password_is_stored_as_a_hash(app):
    from models import User

    with app.app_context():
        user = User.query.filter_by(username="test_admin").first()
        assert user.password_hash != "test-password"
        assert user.check_password("test-password")
        assert not user.check_password("wrong")
