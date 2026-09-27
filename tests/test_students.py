import numpy as np

from models import FaceEmbedding, Student, db
from services import face_service, student_service
from utils.validation import ValidationError, validate_photo


def student_payload(photo):
    return {"name": "Test Student", "roll_no": "TEST-001", "photo": photo}


def mock_face_encodings(monkeypatch, embeddings):
    monkeypatch.setattr(
        face_service.face_recognition,
        "face_encodings",
        lambda image: embeddings[:1],
    )


def test_valid_student_registration_succeeds(client, api_headers, photo_data, monkeypatch):
    mock_face_encodings(monkeypatch, [np.zeros(128)])
    response = client.post("/api/students", json=student_payload(photo_data), headers=api_headers)
    assert response.status_code == 200


def test_duplicate_roll_number_returns_400(client, api_headers, photo_data, monkeypatch):
    mock_face_encodings(monkeypatch, [np.zeros(128)])
    payload = student_payload(photo_data)
    assert client.post("/api/students", json=payload, headers=api_headers).status_code == 200
    response = client.post("/api/students", json=payload, headers=api_headers)
    assert response.status_code == 400


def test_no_face_returns_400(client, api_headers, photo_data, monkeypatch):
    monkeypatch.setattr(
        student_service,
        "create_face_embeddings",
        lambda photos: (_ for _ in ()).throw(ValidationError("Photo must contain a detectable face")),
    )
    response = client.post("/api/students", json=student_payload(photo_data), headers=api_headers)
    assert response.status_code == 400


def test_missing_photo_returns_400(client, api_headers):
    response = client.post(
        "/api/students",
        json={"name": "Test Student", "roll_no": "TEST-001"},
        headers=api_headers,
    )
    assert response.status_code == 400


def test_multiple_valid_photos_create_multiple_embeddings(client, api_headers, photo_data, monkeypatch):
    embeddings = [np.zeros(128), np.ones(128)]
    calls = iter(embeddings)
    monkeypatch.setattr(
        face_service.face_recognition,
        "face_encodings",
        lambda image: [next(calls)],
    )
    response = client.post(
        "/api/recognition/register",
        json={"name": "Multi Photo", "roll_no": "MULTI-001", "photos": [photo_data, photo_data]},
        headers=api_headers,
    )
    assert response.status_code == 200
    with client.application.app_context():
        student = Student.query.filter_by(roll_no="MULTI-001").first()
        assert student is not None
        assert len(student.face_embeddings) == 2


def test_invalid_image_is_skipped_when_valid_photo_exists(client, api_headers, photo_data, monkeypatch):
    mock_face_encodings(monkeypatch, [np.zeros(128)])
    response = client.post(
        "/api/recognition/register",
        json={"name": "Mixed Photos", "roll_no": "MIXED-001", "photos": ["invalid", photo_data]},
        headers=api_headers,
    )
    assert response.status_code == 200


def test_registration_rolls_back_when_commit_fails(client, api_headers, photo_data, monkeypatch):
    mock_face_encodings(monkeypatch, [np.zeros(128)])
    original_commit = db.session.commit
    monkeypatch.setattr(db.session, "commit", lambda: (_ for _ in ()).throw(RuntimeError("commit failed")))
    response = client.post("/api/students", json=student_payload(photo_data), headers=api_headers)
    monkeypatch.setattr(db.session, "commit", original_commit)
    assert response.status_code == 500
    with client.application.app_context():
        assert Student.query.filter_by(roll_no="TEST-001").first() is None
        assert not list(student_service.KNOWN_DIR.glob("Test Student_TEST-001.jpg"))
