from models import Student, User, db


def role_headers(client, app, username, role, student_id=None):
    with app.app_context():
        user = User(username=username, role=role, student_id=student_id)
        user.set_password("role-password")
        db.session.add(user)
        db.session.commit()
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": "role-password"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json['token']}"}


def test_unauthenticated_request_returns_401(client):
    assert client.get("/api/analytics/overview").status_code == 401


def test_admin_can_access_admin_only_endpoint(client, app):
    headers = role_headers(client, app, "rbac-admin", "ADMIN")
    response = client.post("/api/reload_faces", headers=headers)
    assert response.status_code == 200


def test_teacher_can_view_attendance_but_not_reload_faces(client, app):
    headers = role_headers(client, app, "rbac-teacher", "TEACHER")
    assert client.get("/api/attendance", headers=headers).status_code == 200
    assert client.post("/api/reload_faces", headers=headers).status_code == 403


def test_student_cannot_register_or_mark_attendance(client, app):
    headers = role_headers(client, app, "rbac-student", "STUDENT")
    assert client.post("/api/students", json={}, headers=headers).status_code == 403
    assert client.post("/api/attendance", json={}, headers=headers).status_code == 403


def test_student_can_access_only_own_profile_and_analytics(client, app):
    with app.app_context():
        student = Student(name="RBAC Student", roll_no="RBAC-001")
        db.session.add(student)
        db.session.flush()
        student_id = student.id
        db.session.commit()
    headers = role_headers(client, app, "rbac-self", "STUDENT", student_id)
    assert client.get(f"/api/students/{student_id}", headers=headers).status_code == 200
    assert client.get(f"/api/analytics/student/{student_id}", headers=headers).status_code == 200
    assert client.get(f"/api/students/{student_id + 1}", headers=headers).status_code == 403