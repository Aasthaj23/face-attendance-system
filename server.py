import os
import json
import base64
import io
import numpy as np
from datetime import datetime, timedelta
from PIL import Image
from flask import Flask, render_template, request, jsonify, redirect, send_from_directory, send_file
from flask_cors import CORS
from flask_jwt_extended import (
    JWTManager,
    create_access_token,
    verify_jwt_in_request
)
from flask_sqlalchemy import SQLAlchemy

# ── App setup ─────────────────────────────────────────────────────────
app = Flask(__name__)

app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY", "4cf445c9cf0a1de286c0b537e5dfcf1d8eeaff8a02380532c1e041c15127bc24")
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=2)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///attendance.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
jwt = JWTManager(app)
CORS(app)

# ── Settings ──────────────────────────────────────────────────────────
API_KEY    = os.environ.get("API_KEY", "85ba7587e257e99ac59ad97a3e6c1ebfba1a0318ced994a895d4f9f13b28ce7d")
KNOWN_DIR  = "Known"
STUDENTS_FILE = "students.json"

# ── Hardcoded subjects ─────────────────────────────────────────────────
SUBJECTS = [
    "Mathematics",
    "Physics",
    "Chemistry",
    "Computer Science",
    "English",
    "Physical Education"
]

ATTENDANCE_THRESHOLD = 75  # % below which a warning is shown

os.makedirs(KNOWN_DIR, exist_ok=True)

# ── Face recognition setup ────────────────────────────────────────────
try:
    import face_recognition
    FACE_RECOGNITION_AVAILABLE = True
except ImportError:
    FACE_RECOGNITION_AVAILABLE = False

known_encodings = []
known_names     = []

def load_known_faces():
    known_encodings.clear()
    known_names.clear()

    if not FACE_RECOGNITION_AVAILABLE:
        return

    students = load_students()

    for student in students:
        filename = student.get("filename")
        if not filename:
            continue

        path = os.path.join(KNOWN_DIR, filename)
        if not os.path.exists(path):
            continue

        try:
            img = Image.open(path).convert("RGB")
            img_array = np.array(img, dtype=np.uint8)
            encs = face_recognition.face_encodings(img_array)

            if encs:
                known_encodings.append(encs[0])
                known_names.append(student["name"])
        except Exception as e:
            print(f"Error loading {filename}: {e}")

# ── Models ────────────────────────────────────────────────────────────
class AttendanceRecord(db.Model):
    id        = db.Column(db.Integer, primary_key=True)
    name      = db.Column(db.String(100), nullable=False)
    roll_no   = db.Column(db.String(50),  nullable=True)
    subject   = db.Column(db.String(100), nullable=True, default="General")
    timestamp = db.Column(db.String(50),  nullable=False)
    status    = db.Column(db.String(20),  nullable=False)

with app.app_context():
    db.create_all()
    # Add columns if upgrading from old DB (safe migration)
    try:
        with db.engine.connect() as conn:
            conn.execute(db.text("ALTER TABLE attendance_record ADD COLUMN roll_no VARCHAR(50)"))
            conn.commit()
    except Exception:
        pass
    try:
        with db.engine.connect() as conn:
            conn.execute(db.text("ALTER TABLE attendance_record ADD COLUMN subject VARCHAR(100) DEFAULT 'General'"))
            conn.commit()
    except Exception:
        pass

# ── Helpers ───────────────────────────────────────────────────────────
def load_students():
    try:
        with open(STUDENTS_FILE, "r") as f:
            return json.load(f)
    except:
        return []

def save_students(students):
    with open(STUDENTS_FILE, "w") as f:
        json.dump(students, f, indent=2)

def is_jwt_valid():
    try:
        verify_jwt_in_request()
        return True
    except:
        return False

def date_range_filter(query, range_type):
    now   = datetime.now()
    today = now.strftime("%Y-%m-%d")
    if range_type == "day":
        return query.filter(AttendanceRecord.timestamp.startswith(today))
    elif range_type == "week":
        week_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d")
        return query.filter(AttendanceRecord.timestamp >= week_ago)
    elif range_type == "month":
        month_ago = (now - timedelta(days=30)).strftime("%Y-%m-%d")
        return query.filter(AttendanceRecord.timestamp >= month_ago)
    return query  # "all"

# ── Page Routes ───────────────────────────────────────────────────────
@app.route("/")
def login_page():
    return render_template("login.html")

@app.route("/dashboard")
def dashboard():
    return render_template("attendance.html")

@app.route("/students")
def students_page():
    return render_template("students.html")

# Serve student photos
@app.route("/api/photo/<roll_no>")
def get_photo(roll_no):
    students = load_students()
    student  = next((s for s in students if s["roll_no"] == roll_no), None)

    if not student:
        return jsonify({"error": "Not found"}), 404

    filepath = os.path.join(KNOWN_DIR, student["filename"])
    if not os.path.exists(filepath):
        return jsonify({"error": "Photo not found"}), 404

    return send_file(filepath, mimetype="image/jpeg")
# ── Auth ──────────────────────────────────────────────────────────────
@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json() or {}
    if data.get("username") == "admin" and data.get("password") == "1234":
        token = create_access_token(identity="admin")
        return jsonify({"token": token, "user": "admin"})
    return jsonify({"error": "Invalid credentials"}), 401

# ── Subjects ──────────────────────────────────────────────────────────
@app.route("/api/subjects")
def get_subjects():
    if not is_jwt_valid():
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(SUBJECTS)

# ── Students ──────────────────────────────────────────────────────────
@app.route("/api/students", methods=["GET", "POST"])
def handle_students():
    if not is_jwt_valid():
        return jsonify({"error": "Unauthorized"}), 401

    if request.method == "POST":
        data        = request.get_json() or {}
        name        = data.get("name")
        roll        = data.get("roll_no")
        photo       = data.get("photo")

        if not name or not roll or not photo:
            return jsonify({"error": "Missing fields"}), 400

        try:
            header, encoded = photo.split(",", 1)
            img_bytes = base64.b64decode(encoded)
            img       = Image.open(io.BytesIO(img_bytes)).convert("RGB")

            if FACE_RECOGNITION_AVAILABLE:
                encs = face_recognition.face_encodings(np.array(img))
                if not encs:
                    return jsonify({"error": "No face detected in the photo"}), 400

            safe_name = "".join(c for c in name if c.isalnum() or c in (" ", "_", "-")).strip().replace(" ", "_")
            safe_roll = "".join(c for c in roll if c.isalnum() or c in ("_", "-")).strip()
            filename = f"{safe_name}_{safe_roll}.jpg"
            img.save(os.path.join(KNOWN_DIR, filename), "JPEG")

            students = load_students()
            # Prevent duplicate roll numbers
            if any(s["roll_no"] == roll for s in students):
                return jsonify({"error": "Roll number already exists"}), 400

            students.append({
                "name":     name,
                "roll_no":  roll,
                "filename": filename,
                "added_on": datetime.now().isoformat()
            })
            save_students(students)
            load_known_faces()
            return jsonify({"message": "Student registered successfully"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # GET — include attendance stats per student
    students  = load_students()
    all_records = AttendanceRecord.query.all()

    result = []
    for s in students:
        student_records = [r for r in all_records if r.roll_no == s["roll_no"] or r.name == s["name"]]
        total   = len(student_records)
        present = len([r for r in student_records if r.status == "present"])
        pct     = round((present / total * 100) if total > 0 else 0)
        result.append({
            **s,
            "total_classes": total,
            "present_count": present,
            "attendance_pct": pct,
            "below_threshold": pct < ATTENDANCE_THRESHOLD and total > 0
        })

    return jsonify(result)

@app.route("/api/students/<roll_no>", methods=["DELETE"])
def delete_student(roll_no):
    if not is_jwt_valid():
        return jsonify({"error": "Unauthorized"}), 401
    students = load_students()
    student  = next((s for s in students if s["roll_no"] == roll_no), None)
    if student:
        path = os.path.join(KNOWN_DIR, student["filename"])
        if os.path.exists(path):
            os.remove(path)
        students = [s for s in students if s["roll_no"] != roll_no]
        save_students(students)
        load_known_faces()
        return jsonify({"message": "Student deleted"})
    return jsonify({"error": "Not found"}), 404

# ── Attendance Records ────────────────────────────────────────────────
@app.route("/api/full_records")
def full_records():
    if not is_jwt_valid():
        return jsonify({"error": "Unauthorized"}), 401

    range_type = request.args.get("range", "all")   # day | week | month | all
    subject    = request.args.get("subject", "")     # filter by subject

    query = AttendanceRecord.query
    query = date_range_filter(query, range_type)

    if subject and subject != "all":
        query = query.filter(AttendanceRecord.subject == subject)

    rows    = query.order_by(AttendanceRecord.id.desc()).all()
    records = []
    for r in rows:
        records.append({
            "id":      r.id,
            "name":    r.name,
            "roll_no": r.roll_no or "",
            "subject": r.subject or "General",
            "date":    r.timestamp.split(" ")[0],
            "time":    r.timestamp.split(" ")[1] if " " in r.timestamp else "",
            "status":  r.status
        })
    return jsonify(records)

# ── Manual Override ───────────────────────────────────────────────────
@app.route("/api/records/<int:record_id>/toggle", methods=["POST"])
def toggle_record(record_id):
    if not is_jwt_valid():
        return jsonify({"error": "Unauthorized"}), 401
    record = AttendanceRecord.query.get(record_id)
    if not record:
        return jsonify({"error": "Record not found"}), 404
    record.status = "absent" if record.status == "present" else "present"
    db.session.commit()
    return jsonify({"id": record.id, "status": record.status})

# ── Manual Add Record ─────────────────────────────────────────────────
@app.route("/api/records", methods=["POST"])
def add_record():
    if not is_jwt_valid():
        return jsonify({"error": "Unauthorized"}), 401
    data    = request.get_json() or {}
    name    = data.get("name")
    roll_no = data.get("roll_no", "")
    subject = data.get("subject", "General")
    status  = data.get("status", "present")
    date    = data.get("date", datetime.now().strftime("%Y-%m-%d"))
    time    = data.get("time", datetime.now().strftime("%H:%M:%S"))

    if not name:
        return jsonify({"error": "Name is required"}), 400

    record = AttendanceRecord(
        name      = name,
        roll_no   = roll_no,
        subject   = subject,
        timestamp = f"{date} {time}",
        status    = status
    )
    db.session.add(record)
    db.session.commit()
    return jsonify({"message": "Record added", "id": record.id})

# ── Status ────────────────────────────────────────────────────────────
@app.route("/api/status")
def api_status():
    today = datetime.now().strftime("%Y-%m-%d")
    count = AttendanceRecord.query.filter(
        AttendanceRecord.timestamp.startswith(today)
    ).count()
    return jsonify({
        "marked_today":   count,
        "known_faces":    len(known_names),
        "total_students": len(load_students()),
        "subjects":       SUBJECTS,
        "threshold":      ATTENDANCE_THRESHOLD
    })

@app.route("/api/detect", methods=["POST"])
def detect():
    # API Key security (for camera)
    api_key = request.headers.get("X-API-Key")
    if api_key != API_KEY:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json() or {}
    name = data.get("name", "").strip()

    if not name:
        return jsonify({"error": "No name provided"}), 400

    now = datetime.now()
    today = now.strftime("%Y-%m-%d")

    # Check duplicate (same day)
    existing = AttendanceRecord.query.filter(
        AttendanceRecord.name == name,
        AttendanceRecord.timestamp.startswith(today)
    ).first()

    if existing:
        return jsonify({
            "status": "duplicate",
            "message": "Already marked today"
        })

    # ✅ Only PRESENT (as you wanted)
    record = AttendanceRecord(
        name=name,
        roll_no="",
        subject="General",
        timestamp=now.strftime("%Y-%m-%d %H:%M:%S"),
        status="present"
    )

    db.session.add(record)
    db.session.commit()

    print(f"[+] Marked: {name} (present)")

    return jsonify({
        "status": "present",
        "name": name
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)