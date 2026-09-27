from services.liveness_service import LivenessSessionStore, LivenessTracker


def test_left_turn_completes_challenge():
    tracker = LivenessTracker()
    neutral = {
        "nose_tip": [(50, 50)],
        "left_eye": [(40, 45)],
        "right_eye": [(60, 45)],
    }
    turned_left = {
        "nose_tip": [(47, 50)],
        "left_eye": [(40, 45)],
        "right_eye": [(60, 45)],
    }

    assert tracker.update((100, 100), neutral) is False
    assert tracker.update((101, 100), turned_left) is True


def test_missing_landmarks_do_not_complete_challenge():
    tracker = LivenessTracker()
    assert tracker.update((100, 100), {}) is False


def test_liveness_session_requires_two_frames():
    store = LivenessSessionStore()
    session_id = store.start()
    neutral = {
        "nose_tip": [(50, 50)],
        "left_eye": [(40, 45)],
        "right_eye": [(60, 45)],
    }
    turned_left = {
        "nose_tip": [(47, 50)],
        "left_eye": [(40, 45)],
        "right_eye": [(60, 45)],
    }
    assert store.update(session_id, (100, 100), neutral) is False
    assert store.update(session_id, (101, 100), turned_left) is True
    assert store.update(session_id, (101, 100), turned_left) is False