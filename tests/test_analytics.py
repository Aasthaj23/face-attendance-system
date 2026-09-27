from datetime import date, datetime

from models import Attendance, Student, Subject, db


def seed_records(app):
    with app.app_context():
        student_one = Student(name="Analytics One", roll_no="AN-001")
        student_two = Student(name="Analytics Two", roll_no="AN-002")
        subject = Subject.query.filter_by(name="Mathematics").first()
        db.session.add_all([student_one, student_two])
        db.session.flush()
        db.session.add_all([
            Attendance(
                student_id=student_one.id,
                subject_id=subject.id,
                date=date.today(),
                timestamp=datetime.now(),
                status="present",
            ),
            Attendance(
                student_id=student_two.id,
                subject_id=subject.id,
                date=date.today(),
                timestamp=datetime.now(),
                status="late",
            ),
            Attendance(
                student_id=student_one.id,
                subject_id=subject.id,
                date=date(2026, 8, 10),
                timestamp=datetime(2026, 8, 10, 9),
                status="absent",
            ),
        ])
        db.session.commit()
        return student_one.id, student_two.id, subject.id


def test_analytics_requires_authorization(client):
    assert client.get("/api/analytics/overview").status_code == 401


def test_overview_returns_daily_summary(client, api_headers, app):
    seed_records(app)
    response = client.get("/api/analytics/overview", headers=api_headers)
    assert response.status_code == 200
    assert response.json["present_today"] == 2
    assert response.json["late_today"] == 1
    assert response.json["absent_today"] == response.json["total_students"] - 2
    assert response.json["overall_percentage"] == round(2 / response.json["total_students"] * 100)


def test_student_and_subject_analytics(client, api_headers, app):
    student_id, _, subject_id = seed_records(app)
    student = client.get(f"/api/analytics/student/{student_id}", headers=api_headers)
    subject = client.get(f"/api/analytics/subject/{subject_id}", headers=api_headers)
    assert student.status_code == 200
    assert student.json["present"] == 1
    assert student.json["absent"] == 1
    assert subject.status_code == 200
    assert subject.json["late"] == 1
    assert subject.json["total_records"] == 3


def test_monthly_analytics_returns_month_buckets(client, api_headers, app):
    seed_records(app)
    response = client.get("/api/analytics/monthly?year=2026", headers=api_headers)
    assert response.status_code == 200
    assert len(response.json["months"]) == 12
    august = next(item for item in response.json["months"] if item["month"] == "2026-08")
    assert august["absent"] == 1


def test_monthly_analytics_rejects_invalid_year(client, api_headers):
    response = client.get("/api/analytics/monthly?year=not-a-year", headers=api_headers)
    assert response.status_code == 400
