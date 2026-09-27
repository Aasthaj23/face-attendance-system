def test_correct_credentials_return_200(client):
    response = client.post("/api/login", json={"username": "admin", "password": "1234"})
    assert response.status_code == 200
    assert response.json["token"]


def test_wrong_credentials_return_401(client):
    response = client.post("/api/login", json={"username": "admin", "password": "wrong"})
    assert response.status_code == 401


def test_missing_token_returns_401(client):
    response = client.get("/api/students")
    assert response.status_code == 401
