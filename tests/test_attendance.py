def detect(client, headers, name="Attendance Student", subject="Mathematics"):
    return client.post(
        "/api/detect",
        json={"name": name, "subject": subject},
        headers=headers,
    )


def test_first_attendance_is_created(client, api_headers):
    response = detect(client, api_headers)
    assert response.status_code == 200
    assert response.json["status"] == "present"


def test_same_student_subject_date_is_duplicate(client, api_headers):
    assert detect(client, api_headers).json["status"] == "present"
    response = detect(client, api_headers)
    assert response.status_code == 200
    assert response.json["status"] == "duplicate"


def test_manual_toggle_changes_status(client, api_headers):
    record = detect(client, api_headers).json
    response = client.post(f"/api/records/{record['id']}/toggle", headers=api_headers)
    assert response.status_code == 200
    assert response.json["status"] == "absent"
