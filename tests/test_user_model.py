import pytest

from models import User


def test_user_roles_are_restricted(app):
    with app.app_context():
        user = User(username="teacher", password_hash="placeholder")
        user.set_role("TEACHER")
        assert user.role == "TEACHER"
        user.set_role("STUDENT")
        assert user.role == "STUDENT"
        with pytest.raises(ValueError):
            user.set_role("UNKNOWN")