import os
import json
import base64
import io
import numpy as np
from datetime import datetime, timedelta
from PIL import Image

from flask import Flask, render_template, request, jsonify, redirect
from flask_cors import CORS
from flask_jwt_extended import (
    JWTManager,
    create_access_token,
    verify_jwt_in_request
)
from flask_sqlalchemy import SQLAlchemy

# ── App setup ─────────────────────────────────────────────────────────
app = Flask(__name__)

app.config["JWT_SECRET_KEY"]           = os.environ.get("JWT_SECRET_KEY", "4cf445c9cf0a1de286c0b537e5dfcf1d8eeaff8a02380532c1e041c15127bc24")
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=2)
app.config["SQLALCHEMY_DATABASE_URI"]  = "sqlite:///attendance.db"

db  = SQLAlchemy(app)
jwt = JWTManager(app)
CORS(app)

# ── Settings ──────────────────────────────────────────────────────────
API_KEY       = os.environ.get("API_KEY", "85ba7587e257e99ac59ad97a3e6c1ebfba1a0318ced994a895d4f9f13b28ce7d")
KNOWN_DIR     = "Known"
STUDENTS_FILE = "students.json"
THRESHOLD     = 0.5

os.makedirs(KNOWN_DIR, exist_ok=True)

# ── Face recognition (lazy import — only if available) ────────────────
try:
    import face_recognition
    FACE_RECOGNITION_AVAILABLE = True
    print("[✓] face_recognition loaded")
except ImportError:
    FACE_RECOGNITION_AVAILABLE = False
    print("[!] face_recognition not available — photo verification skipped")

# ── Known faces (in memory) ───────────────────────────────────────────
known_encodings: list = []
known_names:     list = []

def load_known_faces() -> None:
    known_encodings.clear()
    known_names.clear()
    if not FACE_RECOGNITION_AVAILABLE:
        return
    for filename in os.listdir(KNOWN_DIR):
        if not filename.lower().endswith((".jpg", ".jpeg", ".png")):
            continue
        path  = os.path.join(KNOWN_DIR, filename)
        name  = os.path.splitext(filename)[0].split("_")[0]
        try:
            img       = Image.open(path).convert("RGB")
            img_array = np.array(img, dtype=np.uint8)
            encs      = face_recognition.face_encodings(img_array)
            if encs:
                known_encodings.append(encs[0])
                known_names.append(name)
                print(f"  ✅ {filename} → {name}")
        except Exception as e:
            print(f"  ❌ Error loading {filename}: {e}")
    print(f"[✓] {len(known_names)} face(s) loaded")

load_known_faces()

# ── Database model ────────────────────────────────────────────────────
class AttendanceRecord(db.Model):
    id        = db.Column(db.Integer,     primary_key=True)
    name      = db.Column(db.String(100), nullable=False)
    timestamp = db.Column(db.String(50),  nullable=False)
    status    = db.Column(db.String(20),  nullable=False)

with app.app_context():
    db.create_all()

# ── Student registry helpers ──────────────────────────────────────────
def load_students() -> list:
    try:
        with open(STUDENTS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []

def save_students(students: list) -> None:
    with open(STUDENTS_FILE, "w") as f:
        json.dump(students, f, indent=2)

def get_student_names() -> list:
    """Returns list of all registered student names for absent tracking."""
    return [s["name"] for s in load_students()]

# ── Auth helpers ──────────────────────────────────────────────────────
def is_api_request_valid(req) -> bool:
    return req.headers.get("X-API-Key") == API_KEY

def is_jwt_valid() -> bool:
    try:
        verify_jwt_in_request()
        return True
    except Exception:
        return False

# ── Attendance helpers ────────────────────────────────────────────────
def already_marked_today(name: str) -> bool:
    today = datetime.now().strftime("%Y-%m-%d")
    return AttendanceRecord.query.filter(
        AttendanceRecord.name == name,
        AttendanceRecord.timestamp.startswith(today)
    ).first() is not None

def write_attendance(name: str, status: str = "present") -> str:
    time_now = datetime.now()
    db.session.add(AttendanceRecord(
        name      = name,
        timestamp = time_now.strftime("%Y-%m-%d %H:%M:%S"),
        status    = status
    ))
    db.session.commit()
    return status

# ── Frontend routes ───────────────────────────────────────────────────
@app.route("/")
def login_page():
    return render_template("login.html")

@app.route("/dashboard")
def dashboard():
    return render_template("attendance.html")

@app.route("/students")
def students_page():
    if not is_jwt_valid():
        return redirect("/")
    return render_template("students.html")

# ── Auth API ──────────────────────────────────────────────────────────
@app.route("/api/login", methods=["POST"])
def api_login():
    data     = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    if username == "admin" and password == "1234":
        token = create_access_token(identity=username)
        return jsonify({"token": token, "user": username})

    return jsonify({"error": "Invalid credentials"}), 401

# ── Student registry API ──────────────────────────────────────────────
@app.route("/api/students", methods=["GET"])
def get_students():
    if not is_jwt_valid() and not is_api_request_valid(request):
        return jsonify({"error": "Unauthorised"}), 401
    return jsonify(load_students())

@app.route("/api/students", methods=["POST"])
def add_student():
    if not is_jwt_valid() and not is_api_request_valid(request):
        return jsonify({"error": "Unauthorised"}), 401

    data    = request.get_json(silent=True) or {}
    name    = data.get("name",    "").strip()
    roll_no = data.get("roll_no", "").strip()
    photo   = data.get("photo",   "")

    # Validate inputs
    if not name:
        return jsonify({"error": "Name is required"}), 400
    if not roll_no:
        return jsonify({"error": "Roll number is required"}), 400
    if not photo:
        return jsonify({"error": "Photo is required"}), 400

    # Check duplicate roll number
    students = load_students()
    if any(s["roll_no"] == roll_no for s in students):
        return jsonify({"error": f"Roll number {roll_no} already exists"}), 409

    try:
        # Decode base64 photo from browser
        if "," in photo:
            _, encoded = photo.split(",", 1)
        else:
            encoded = photo

        img_bytes = base64.b64decode(encoded)
        img       = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        img_array = np.array(img, dtype=np.uint8)

        # Verify face exists in photo (if face_recognition available)
        if FACE_RECOGNITION_AVAILABLE:
            encs = face_recognition.face_encodings(img_array)
            if not encs:
                return jsonify({
                    "error": "No face detected in photo — please use a clear front-facing photo"
                }), 400

        # Save photo to Known/ as "Name_RollNo.jpg"
        filename = f"{name}_{roll_no}.jpg"
        filepath = os.path.join(KNOWN_DIR, filename)
        img.save(filepath, "JPEG", quality=95)

        # Save student record to students.json
        student = {
            "name":     name,
            "roll_no":  roll_no,
            "filename": filename,
            "added_on": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        students.append(student)
        save_students(students)

        # Reload face encodings into memory
        load_known_faces()

        print(f"[+] Student registered: {name} ({roll_no})")
        return jsonify({"message": "Student registered successfully", "student": student}), 200

    except Exception as e:
        print(f"[ERROR] add_student: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/students/<roll_no>", methods=["DELETE"])
def delete_student(roll_no):
    if not is_jwt_valid() and not is_api_request_valid(request):
        return jsonify({"error": "Unauthorised"}), 401

    students = load_students()
    student  = next((s for s in students if s["roll_no"] == roll_no), None)

    if not student:
        return jsonify({"error": "Student not found"}), 404

    # Delete photo from Known/
    filepath = os.path.join(KNOWN_DIR, student["filename"])
    if os.path.exists(filepath):
        os.remove(filepath)
        print(f"[-] Deleted photo: {student['filename']}")

    # Remove from students.json
    students = [s for s in students if s["roll_no"] != roll_no]
    save_students(students)

    # Reload face encodings
    load_known_faces()

    print(f"[-] Student removed: {student['name']} ({roll_no})")
    return jsonify({"message": f"Deleted {student['name']}"}), 200

# ── Attendance API ────────────────────────────────────────────────────
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

    status = write_attendance(name, "present")
    print(f"[+] Marked present: {name}")
    return jsonify({"name": name, "status": status}), 200

@app.route("/api/mark_absent", methods=["POST"])
def mark_absent():
    if not is_jwt_valid() and not is_api_request_valid(request):
        return jsonify({"error": "Unauthorised"}), 401

    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()

    if not name:
        return jsonify({"error": "No name provided"}), 400

    if already_marked_today(name):
        return jsonify({"message": "Already marked today", "status": "duplicate"}), 200

    status = write_attendance(name, "absent")
    print(f"[-] Marked absent: {name}")
    return jsonify({"name": name, "status": status}), 200

@app.route("/api/full_records")
def full_records():
    if not is_jwt_valid() and not is_api_request_valid(request):
        return jsonify({"error": "Unauthorised"}), 401

    today         = datetime.now().strftime("%Y-%m-%d")
    today_display = datetime.now().strftime("%d-%m-%Y")

    # All DB records newest first
    rows = AttendanceRecord.query.order_by(
        AttendanceRecord.id.desc()
    ).all()

    # Who is already marked today (present or absent)
    marked_today = set(
        r.name for r in rows
        if r.timestamp.startswith(today)
    )

    records = []

    # Add all DB records
    for r in rows:
        try:
            dt = datetime.strptime(r.timestamp, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        records.append({
            "name":   r.name,
            "id":     f"STU-{r.name[:3].upper()}",
            "date":   dt.strftime("%d-%m-%Y"),
            "time":   dt.strftime("%I:%M %p"),
            "status": r.status
        })

    # Add absent entries for students not yet marked today
    # Uses students.json — not hardcoded list
    for name in get_student_names():
        if name not in marked_today:
            records.insert(0, {
                "name":   name,
                "id":     f"STU-{name[:3].upper()}",
                "date":   today_display,
                "time":   "—",
                "status": "absent"
            })

    return jsonify(records)

@app.route("/api/status")
def api_status():
    if not is_jwt_valid() and not is_api_request_valid(request):
        return jsonify({"error": "Unauthorised"}), 401

    today = datetime.now().strftime("%Y-%m-%d")
    count = AttendanceRecord.query.filter(
        AttendanceRecord.timestamp.startswith(today)
    ).count()

    return jsonify({
        "marked_today": count,
        "known_faces":  len(known_names),
        "total_students": len(load_students())
    })

@app.route("/api/reload_faces", methods=["POST"])
def reload_faces():
    if not is_jwt_valid() and not is_api_request_valid(request):
        return jsonify({"error": "Unauthorised"}), 401
    load_known_faces()
    return jsonify({
        "message": "Reloaded",
        "loaded":  len(known_names)
    }), 200

# ── Run ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)