from services.liveness_service import LivenessTracker


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