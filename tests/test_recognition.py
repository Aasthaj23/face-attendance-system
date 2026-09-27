import numpy as np

from services import face_service


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
