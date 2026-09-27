from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token


auth_bp = Blueprint("auth", __name__)


@auth_bp.post("/api/auth/login")
@auth_bp.post("/api/login")
def api_login():
    data = request.get_json() or {}
    if data.get("username") == "admin" and data.get("password") == "1234":
        return jsonify({"token": create_access_token(identity="admin"), "user": "admin"})
    return jsonify({"error": "Invalid credentials"}), 401