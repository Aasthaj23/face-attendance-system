import os
import csv
from datetime import datetime, timedelta

from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from flask_jwt_extended import (
    JWTManager,
    create_access_token,
    jwt_required,
    get_jwt_identity,
    verify_jwt_in_request
)
from flask_sqlalchemy import SQLAlchemy

# ── App setup ─────────────────────────────────────────────────────────
app = Flask(__name__)

app.config["JWT_SECRET_KEY"]          = os.environ.get("JWT_SECRET_KEY", "4cf445c9cf0a1de286c0b537e5dfcf1d8eeaff8a02380532c1e041c15127bc24")
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=2)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///attendance.db"  # one DB only

db  = SQLAlchemy(app)
jwt = JWTManager(app)
CORS(app)

# ── API Key (for CV script) ───────────────────────────────────────────
API_KEY = os.environ.get("API_KEY", "85ba7587e257e99ac59ad97a3e6c1ebfba1a0318ced994a895d4f9f13b28ce7d")

def is_api_request_valid(req) -> bool:
    return req.headers.get("X-API-Key") == API_KEY

# ── Database model ────────────────────────────────────────────────────
class AttendanceRecord(db.Model):
    id        = db.Column(db.Integer,     primary_key=True)
    name      = db.Column(db.String(100), nullable=False)
    timestamp = db.Column(db.String(50),  nullable=False)
    status    = db.Column(db.String(20),  nullable=False)

with app.app_context():
    db.create_all()

# ── Helpers ───────────────────────────────────────────────────────────
def already_marked_today(name: str) -> bool:
    today = datetime.now().strftime("%Y-%m-%d")
    return AttendanceRecord.query.filter(
        AttendanceRecord.name == name,
        AttendanceRecord.timestamp.startswith(today)
    ).first() is not None

def write_attendance(name: str) -> str:
    time_now = datetime.now()
    cutoff   = time_now.replace(hour=9, minute=10, second=0, microsecond=0)
    status   = "late" if time_now > cutoff else "present"
    db.session.add(AttendanceRecord(
        name      = name,
        timestamp = time_now.strftime("%Y-%m-%d %H:%M:%S"),
        status    = status
    ))
    db.session.commit()
    return status

def is_jwt_valid() -> bool:
    """Check JWT token from request — returns True/False without raising."""
    try:
        verify_jwt_in_request()
        return True
    except Exception:
        return False

# ── Auth ──────────────────────────────────────────────────────────────
@app.route("/api/login", methods=["POST"])
def api_login():
    data     = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    if username == "admin" and password == "1234":
        token = create_access_token(identity=username)
        return jsonify({"token": token, "user": username})

    return jsonify({"error": "Invalid credentials"}), 401

# ── Frontend routes ───────────────────────────────────────────────────
@app.route("/")
def login_page():
    return render_template("login.html")

@app.route("/dashboard")
def dashboard():
    return render_template("attendance.html")

# ── API: detect / mark attendance ─────────────────────────────────────
# Accepts EITHER a valid JWT (from dashboard) OR a valid API key (from CV script)
@app.route("/api/detect", methods=["POST"])
def detect():
    if not is_jwt_valid() and not is_api_request_valid(request):
        return jsonify({"error": "Unauthorised"}), 401

    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()

    if not name:
        return jsonify({"error": "No name provided"}), 400

    if already_marked_today(name):
        return jsonify({"message": "Already marked today", "status": "duplicate"}), 200

    status = write_attendance(name)
    print(f"[+] Marked: {name} ({status})")
    return jsonify({"name": name, "status": status}), 200

# ── API: full records ─────────────────────────────────────────────────
@app.route("/api/full_records")
def full_records():
    if not is_jwt_valid() and not is_api_request_valid(request):
        return jsonify({"error": "Unauthorised"}), 401

    rows = AttendanceRecord.query.order_by(AttendanceRecord.id.desc()).all()
    return jsonify([{
        "name":   r.name,
        "id":     f"STU-{r.name[:3].upper()}",
        "date":   datetime.strptime(r.timestamp, "%Y-%m-%d %H:%M:%S").strftime("%d-%m-%Y"),
        "time":   datetime.strptime(r.timestamp, "%Y-%m-%d %H:%M:%S").strftime("%I:%M %p"),
        "status": r.status
    } for r in rows])

# ── API: status ───────────────────────────────────────────────────────
@app.route("/api/status")
def status():
    if not is_jwt_valid() and not is_api_request_valid(request):
        return jsonify({"error": "Unauthorised"}), 401

    today = datetime.now().strftime("%Y-%m-%d")
    # FIX: count from DB not CSV
    count = AttendanceRecord.query.filter(
        AttendanceRecord.timestamp.startswith(today)
    ).count()

    return jsonify({
        "marked_today": count
    })

# ── API: reload faces (called by CV script after registration) ────────
@app.route("/api/reload_faces", methods=["POST"])
def reload_faces():
    if not is_jwt_valid() and not is_api_request_valid(request):
        return jsonify({"error": "Unauthorised"}), 401
    # Server doesn't run face recognition — just acknowledge
    return jsonify({"message": "Acknowledged"}), 200

# ── Run ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)