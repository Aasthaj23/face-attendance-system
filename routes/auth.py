from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token

from models import User
from utils.logger import get_logger

auth_bp = Blueprint("auth", __name__)
logger = get_logger(__name__)


@auth_bp.post("/api/auth/login")
@auth_bp.post("/api/login")
def api_login():
    data = request.get_json() or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 401

    user = User.query.filter_by(username=username).first()
    if user and user.check_password(password):
        token = create_access_token(
            identity=str(user.id),
            additional_claims={"username": user.username, "role": user.role},
        )
        logger.info("User authenticated: %s (%s)", user.username, user.role)
        return jsonify({"token": token, "user": user.username, "role": user.role})
    logger.warning("Authentication failed: %s", username or "unknown")
    return jsonify({"error": "Invalid credentials"}), 401