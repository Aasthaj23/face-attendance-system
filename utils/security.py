import hashlib

from flask import current_app, request
from flask_jwt_extended import verify_jwt_in_request

def is_jwt_valid() -> bool:
    try:
        verify_jwt_in_request()
        return True
    except Exception:
        return False


def is_api_key_valid() -> bool:
    return request.headers.get("X-API-Key", "") == current_app.config.get("API_KEY", "")


def authorized() -> bool:
    return is_jwt_valid() or is_api_key_valid()


def photo_token(roll_no: str) -> str:
    secret = current_app.config["PHOTO_SECRET"]
    return hashlib.sha256(f"{secret}:{roll_no}".encode()).hexdigest()[:16]