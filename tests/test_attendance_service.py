from datetime import datetime

from services.attendance_service import determine_status


SCHEDULE = {"start_time": "09:00:00", "late_after_minutes": 15}


def test_determine_status_returns_present_during_grace_period():
    assert determine_status(datetime(2026, 9, 27, 9, 15), SCHEDULE) == "present"


def test_determine_status_returns_late_after_grace_period():
    assert determine_status(datetime(2026, 9, 27, 9, 16), SCHEDULE) == "late"


def test_determine_status_returns_present_before_class():
    assert determine_status(datetime(2026, 9, 27, 8, 30), SCHEDULE) == "present"