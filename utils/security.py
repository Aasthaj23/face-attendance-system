import hashlib

from flask import request
from flask_jwt_extended import verify_jwt_in_request

from config import Config


def is_jwt_valid() -> bool:
    try:
        verify_jwt_in_request()
        return True
    except Exception:
        return False


def is_api_key_valid() -> bool:
    return request.headers.get("X-API-Key", "") == Config.API_KEY


def authorized() -> bool:
    return is_jwt_valid() or is_api_key_valid()


def photo_token(roll_no: str) -> str:
    return hashlib.sha256(f"{Config.PHOTO_SECRET}:{roll_no}".encode()).hexdigest()[:16]