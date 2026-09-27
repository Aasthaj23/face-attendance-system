def test_auth_route_is_namespaced(client):
    response = client.post("/api/auth/login", json={"username": "test_admin", "password": "test-password"})
    assert response.status_code == 200


def test_student_collection_and_id_route(client, api_headers):
    collection = client.get("/api/students", headers=api_headers)
    assert collection.status_code == 200
    assert client.get("/api/students/999999", headers=api_headers).status_code == 404


def test_attendance_collection_and_patch_route(client, api_headers):
    assert client.get("/api/attendance", headers=api_headers).status_code == 200
    response = client.post(
        "/api/attendance",
        json={"name": "Route Student", "subject": "Mathematics"},
        headers=api_headers,
    )
    assert response.status_code == 200
    record_id = response.json["id"]
    response = client.patch(
        f"/api/attendance/{record_id}",
        json={"status": "late"},
        headers=api_headers,
    )
    assert response.status_code == 200
    assert response.json["status"] == "late"


def test_recognition_routes_require_authorization(client):
    assert client.post("/api/recognition/register", json={}).status_code == 401
    assert client.post("/api/recognition/identify", json={}).status_code == 401
