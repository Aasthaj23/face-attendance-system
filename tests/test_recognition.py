import numpy as np

from models import FaceEmbedding, Student, db
from services import face_service
from services.face_service import deserialize_embedding, serialize_embedding


def test_known_face_is_identified(monkeypatch):
    monkeypatch.setattr(face_service, "FACE_RECOGNITION_AVAILABLE", True)
    monkeypatch.setattr(face_service, "known_encodings", [np.zeros(128)])
    monkeypatch.setattr(face_service, "known_names", ["Known Student"])
    monkeypatch.setattr(face_service, "known_student_ids", [7])
    monkeypatch.setattr(
        face_service.face_recognition,
        "face_distance",
        lambda known, face: np.array([0.2]),
    )
    student_id, distance = face_service.recognize_face(np.zeros(128))
    assert student_id == 7
    assert distance == 0.2


def test_unknown_face_returns_none(monkeypatch):
    monkeypatch.setattr(face_service, "FACE_RECOGNITION_AVAILABLE", True)
    monkeypatch.setattr(face_service, "known_encodings", [np.zeros(128)])
    monkeypatch.setattr(face_service, "known_names", ["Known Student"])
    monkeypatch.setattr(face_service, "known_student_ids", [7])
    monkeypatch.setattr(
        face_service.face_recognition,
        "face_distance",
        lambda known, face: np.array([0.9]),
    )
    student_id, distance = face_service.recognize_face(np.zeros(128))
    assert student_id is None
    assert distance == 0.9


def test_invalid_face_encoding_is_handled_safely(monkeypatch):
    monkeypatch.setattr(face_service, "FACE_RECOGNITION_AVAILABLE", True)
    monkeypatch.setattr(face_service, "known_encodings", [np.zeros(128)])
    monkeypatch.setattr(face_service, "known_names", ["Known Student"])
    monkeypatch.setattr(face_service, "known_student_ids", [7])
    student_id, distance = face_service.recognize_face(None)
    assert student_id is None
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


def test_database_embedding_returns_student_id(monkeypatch):
    monkeypatch.setattr(face_service, "FACE_RECOGNITION_AVAILABLE", True)
    monkeypatch.setattr(face_service, "known_encodings", [np.zeros(128)])
    monkeypatch.setattr(face_service, "known_names", ["Similar Name"])
    monkeypatch.setattr(face_service, "known_student_ids", [42])
    monkeypatch.setattr(
        face_service.face_recognition,
        "face_distance",
        lambda known, face: np.array([0.38]),
    )
    identifier, distance = face_service.recognize_face(np.zeros(128))
    assert identifier == 42
    assert distance == 0.38


def test_legacy_name_only_match_is_not_returned(monkeypatch):
    monkeypatch.setattr(face_service, "FACE_RECOGNITION_AVAILABLE", True)
    monkeypatch.setattr(face_service, "known_encodings", [np.zeros(128)])
    monkeypatch.setattr(face_service, "known_names", ["Duplicate Name"])
    monkeypatch.setattr(face_service, "known_student_ids", [None])
    monkeypatch.setattr(
        face_service.face_recognition,
        "face_distance",
        lambda known, face: np.array([0.2]),
    )
    student_id, distance = face_service.recognize_face(np.zeros(128))
    assert student_id is None
    assert distance == 0.2
