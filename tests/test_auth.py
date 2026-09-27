def test_correct_credentials_return_200(client):
    response = client.post("/api/login", json={"username": "admin", "password": "1234"})
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
        user = User.query.filter_by(username="admin").first()
        assert user.password_hash != "1234"
        assert user.check_password("1234")
        assert not user.check_password("wrong")
