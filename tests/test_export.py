def test_export_requires_authorization(client):
    response = client.get("/api/attendance/export")
    assert response.status_code == 401


def test_export_returns_requested_csv(client, api_headers):
    client.post(
        "/api/attendance",
        json={
            "name": "Export Student",
            "roll_no": "EXP-001",
            "subject": "Mathematics",
            "date": "2026-09-27",
            "time": "09:15:00",
            "status": "present",
        },
        headers=api_headers,
    )
    response = client.get("/api/attendance/export", headers=api_headers)
    assert response.status_code == 200
    assert response.content_type == "text/csv; charset=utf-8"
    assert response.headers["Content-Disposition"].startswith("attachment; filename=attendance.csv")
    assert response.data.decode("utf-8-sig").splitlines() == [
        "Date,Student,Roll No,Subject,Time,Status",
        "2026-09-27,Export Student,EXP-001,Mathematics,09:15:00,present",
    ]
