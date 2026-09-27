import routes.students as students_route


def student_payload(photo):
    return {"name": "Test Student", "roll_no": "TEST-001", "photo": photo}


def test_valid_student_registration_succeeds(client, api_headers, photo_data):
    response = client.post("/api/students", json=student_payload(photo_data), headers=api_headers)
    assert response.status_code == 200


def test_duplicate_roll_number_returns_400(client, api_headers, photo_data):
    payload = student_payload(photo_data)
    assert client.post("/api/students", json=payload, headers=api_headers).status_code == 200
    response = client.post("/api/students", json=payload, headers=api_headers)
    assert response.status_code == 400


def test_no_face_returns_400(client, api_headers, photo_data, monkeypatch):
    monkeypatch.setattr(students_route, "FACE_RECOGNITION_AVAILABLE", True)
    monkeypatch.setattr(students_route, "has_face", lambda image: False)
    response = client.post("/api/students", json=student_payload(photo_data), headers=api_headers)
    assert response.status_code == 400


def test_missing_photo_returns_400(client, api_headers):
    response = client.post(
        "/api/students",
        json={"name": "Test Student", "roll_no": "TEST-001"},
        headers=api_headers,
    )
    assert response.status_code == 400
