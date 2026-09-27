from functools import wraps

from flask import jsonify, request
from flask_jwt_extended import get_jwt, get_jwt_identity, verify_jwt_in_request

from models import User, db
from utils.security import is_api_key_valid



def _forbidden():
    return jsonify({"error": "Forbidden"}), 403


def require_role(*allowed_roles):
    allowed = {role.upper() for role in allowed_roles}

    def decorator(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            if is_api_key_valid():
                return function(*args, **kwargs)
            try:
                verify_jwt_in_request()
            except Exception:
                return jsonify({"error": "Unauthorized"}), 401
            role = str(get_jwt().get("role", "")).upper()
            if role not in allowed:
                return _forbidden()
            return function(*args, **kwargs)

        return wrapped

    return decorator


def require_student_access(student_id_parameter="student_id"):
    def decorator(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            if is_api_key_valid():
                return function(*args, **kwargs)
            try:
                verify_jwt_in_request()
            except Exception:
                return jsonify({"error": "Unauthorized"}), 401
            claims = get_jwt()
            role = str(claims.get("role", "")).upper()
            if role in {"ADMIN", "TEACHER"}:
                return function(*args, **kwargs)
            if role != "STUDENT":
                return _forbidden()
            user = db.session.get(User, get_jwt_identity())
            requested_student_id = kwargs.get(student_id_parameter)
            if not user or user.student_id != requested_student_id:
                return _forbidden()
            return function(*args, **kwargs)

        return wrapped

    return decorator
