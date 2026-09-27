"""Simple challenge-response liveness checks for the camera client."""

import math
import uuid


LIVENESS_CHALLENGE = "Turn your head slightly left."
NOSE_SHIFT_THRESHOLD = 0.12
TRACK_MAX_DISTANCE = 80.0


def _nose_position(landmarks: dict):
    nose = landmarks.get("nose_tip", [])
    left_eye = landmarks.get("left_eye", [])
    right_eye = landmarks.get("right_eye", [])
    if not nose or not left_eye or not right_eye:
        return None

    nose_x = sum(point[0] for point in nose) / len(nose)
    eye_center = (
        sum(point[0] for point in left_eye + right_eye)
        / (len(left_eye) + len(right_eye))
    )
    eye_span = abs(
        sum(point[0] for point in right_eye) / len(right_eye)
        - sum(point[0] for point in left_eye) / len(left_eye)
    )
    if eye_span <= 0:
        return None
    return (nose_x - eye_center) / eye_span


class LivenessTracker:
    """Track face movement and complete a screen-left head-turn challenge."""

    def __init__(self):
        self._sessions = []

    def reset(self) -> None:
        self._sessions.clear()

    def update(self, centroid, landmarks: dict) -> bool:
        position = _nose_position(landmarks)
        if position is None:
            return False

        session = self._find_session(centroid)
        if session is None:
            session = {"centroid": centroid, "baseline": position, "live": False}
            self._sessions.append(session)
            return False

        session["centroid"] = centroid
        if position - session["baseline"] <= -NOSE_SHIFT_THRESHOLD:
            session["live"] = True
        return session["live"]

    def _find_session(self, centroid):
        closest = None
        closest_distance = TRACK_MAX_DISTANCE
        for session in self._sessions:
            distance = math.hypot(
                centroid[0] - session["centroid"][0],
                centroid[1] - session["centroid"][1],
            )
            if distance <= closest_distance:
                closest = session
                closest_distance = distance
        return closest


class LivenessSessionStore:
    """Keep short-lived challenge state between recognition API frames."""

    def __init__(self):
        self._sessions = {}

    def start(self) -> str:
        session_id = uuid.uuid4().hex
        self._sessions[session_id] = LivenessTracker()
        return session_id

    def update(self, session_id: str, centroid, landmarks: dict) -> bool:
        tracker = self._sessions.get(session_id)
        if tracker is None:
            return False
        live = tracker.update(centroid, landmarks)
        if live:
            self._sessions.pop(session_id, None)
        return live

    def discard(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)