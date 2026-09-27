import numpy as np

from models import FaceEmbedding, Student, db
from services import face_service
from services.face_service import deserialize_embedding, serialize_embedding


def test_known_face_is_identified(monkeypatch):
    monkeypatch.setattr(face_service, "FACE_RECOGNITION_AVAILABLE", True)
    monkeypatch.setattr(face_service, "known_encodings", [np.zeros(128)])
    monkeypatch.setattr(face_service, "known_names", ["Known Student"])
    monkeypatch.setattr(
        face_service.face_recognition,
        "face_distance",
        lambda known, face: np.array([0.2]),
    )
    name, distance = face_service.recognize_face(np.zeros(128))
    assert name == "Known Student"
    assert distance == 0.2


def test_unknown_face_returns_none(monkeypatch):
    monkeypatch.setattr(face_service, "FACE_RECOGNITION_AVAILABLE", True)
    monkeypatch.setattr(face_service, "known_encodings", [np.zeros(128)])
    monkeypatch.setattr(face_service, "known_names", ["Known Student"])
    monkeypatch.setattr(
        face_service.face_recognition,
        "face_distance",
        lambda known, face: np.array([0.9]),
    )
    name, distance = face_service.recognize_face(np.zeros(128))
    assert name is None
    assert distance == 0.9


def test_invalid_face_encoding_is_handled_safely(monkeypatch):
    monkeypatch.setattr(face_service, "FACE_RECOGNITION_AVAILABLE", True)
    monkeypatch.setattr(face_service, "known_encodings", [np.zeros(128)])
    monkeypatch.setattr(face_service, "known_names", ["Known Student"])
    name, distance = face_service.recognize_face(None)
    assert name is None
    assert distance == float("inf")


def test_face_embedding_round_trip():
    embedding = np.arange(128, dtype=np.float64)
    restored = deserialize_embedding(serialize_embedding(embedding))
    assert np.array_equal(restored, embedding)


def test_student_has_multiple_face_embeddings(app):
    with app.app_context():
        student = Student(name="Multi Sample", roll_no="MULTI-001")
        student.face_embeddings = [
            FaceEmbedding(embedding=serialize_embedding(np.zeros(128))),
            FaceEmbedding(embedding=serialize_embedding(np.ones(128))),
        ]
        db.session.add(student)
        db.session.commit()
        assert len(student.face_embeddings) == 2
