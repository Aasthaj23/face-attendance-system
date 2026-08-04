import os
import json
import base64
import io
import hashlib
from datetime import datetime, timedelta
from functools import lru_cache

from flask import Flask, render_template, request, jsonify, redirect, send_from_directory, abort
from flask_cors import CORS
from flask_jwt_extended import JWTManager, create_access_token, verify_jwt_in_request
from flask_sqlalchemy import SQLAlchemy
from PIL import Image

# ── App ───────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config.update(
    JWT_SECRET_KEY           = os.environ.get("JWT_SECRET_KEY", "4cf445c9cf0a1de286c0b537e5dfcf1d8eeaff8a02380532c1e041c15127bc24"),
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=2),
    SQLALCHEMY_DATABASE_URI  = "sqlite:///attendance.db",
    SQLALCHEMY_TRACK_MODIFICATIONS = False,
)

db  = SQLAlchemy(app)
jwt = JWTManager(app)
CORS(app)

# ── Constants ─────────────────────────────────────────────────────────
API_KEY              = os.environ.get("API_KEY", "85ba7587e257e99ac59ad97a3e6c1ebfba1a0318ced994a895d4f9f13b28ce7d")
PHOTO_SECRET         = os.environ.get("PHOTO_SECRET", "photo_secret_key_changeme")
KNOWN_DIR            = "Known"
STUDENTS_FILE        = "students.json"
ATTENDANCE_THRESHOLD = 75
SUBJECTS             = ["Mathematics", "Physics", "Chemistry", "Computer Science", "English", "Physical Education"]

os.makedirs(KNOWN_DIR, exist_ok=True)

# ── Face recognition ──────────────────────────────────────────────────
try:
    import face_recognition
    import numpy as np
    FACE_RECOGNITION_AVAILABLE = True
except ImportError:
    FACE_RECOGNITION_AVAILABLE = False

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
        path = os.path.join(KNOWN_DIR, filename)
        name = os.path.splitext(filename)[0].rsplit("_", 1)[0]
        try:
            img_array = np.array(Image.open(path).convert("RGB"), dtype=np.uint8)
            encs      = face_recognition.face_encodings(img_array)
            if encs:
                known_encodings.append(encs[0])
                known_names.append(name)
        except Exception as e:
            print(f"[faces] Error loading {filename}: {e}")
    print(f"[faces] {len(known_names)} loaded")

load_known_faces()

# ── Model ─────────────────────────────────────────────────────────────
class AttendanceRecord(db.Model):
    id        = db.Column(db.Integer,     primary_key=True)
    name      = db.Column(db.String(100), nullable=False, index=True)
    roll_no   = db.Column(db.String(50),  nullable=True,  index=True)
    subject   = db.Column(db.String(100), nullable=True,  default="General")
    timestamp = db.Column(db.String(50),  nullable=False, index=True)
    status    = db.Column(db.String(20),  nullable=False)

with app.app_context():
    db.create_all()
    # Safe column migrations for existing DBs
    for col_sql in [
        "ALTER TABLE attendance_record ADD COLUMN roll_no VARCHAR(50)",
        "ALTER TABLE attendance_record ADD COLUMN subject VARCHAR(100) DEFAULT 'General'",
    ]:
        try:
            with db.engine.connect() as conn:
                conn.execute(db.text(col_sql))
                conn.commit()
        except Exception:
            pass

# ── Auth helpers ──────────────────────────────────────────────────────
def is_jwt_valid() -> bool:
    try:
        verify_jwt_in_request()
        return True
    except Exception:
        return False

def is_api_key_valid() -> bool:
    return request.headers.get("X-API-Key", "") == API_KEY

def authorized() -> bool:
    """True if request carries valid JWT or API key."""
    return is_jwt_valid() or is_api_key_valid()

def photo_token(roll_no: str) -> str:
    return hashlib.sha256(f"{PHOTO_SECRET}:{roll_no}".encode()).hexdigest()[:16]

# ── Student helpers ───────────────────────────────────────────────────
def load_students() -> list:
    try:
        with open(STUDENTS_FILE) as f:
            return json.load(f)
    except Exception:
        return []

def save_students(students: list) -> None:
    with open(STUDENTS_FILE, "w") as f:
        json.dump(students, f, indent=2)

def find_student(students: list, *, roll_no: str = "", name: str = "") -> dict | None:
    """Look up by roll_no first, fall back to case-insensitive name."""
    if roll_no:
        match = next((s for s in students if s["roll_no"] == roll_no), None)
        if match:
            return match
    if name:
        nl = name.lower()
        return next((s for s in students if s["name"].lower() == nl), None)
    return None

def decode_photo(photo_data: str) -> Image.Image:
    """Decode a base64 data-URI or raw base64 string into a PIL Image."""
    if "," in photo_data:
        photo_data = photo_data.split(",", 1)[1]
    return Image.open(io.BytesIO(base64.b64decode(photo_data))).convert("RGB")

# ── Attendance helpers ────────────────────────────────────────────────
def already_marked(roll_no: str, name: str, subject: str, today: str) -> bool:
    q = AttendanceRecord.query.filter(
        AttendanceRecord.timestamp.startswith(today),
        AttendanceRecord.subject == subject,
    )
    q = q.filter(AttendanceRecord.roll_no == roll_no) if roll_no \
        else q.filter(AttendanceRecord.name == name)
    return q.first() is not None

def date_range_filter(query, range_type: str):
    now = datetime.now()
    if range_type == "day":
        return query.filter(AttendanceRecord.timestamp.startswith(now.strftime("%Y-%m-%d")))
    if range_type == "week":
        return query.filter(AttendanceRecord.timestamp >= (now - timedelta(days=7)).strftime("%Y-%m-%d"))
    if range_type == "month":
        return query.filter(AttendanceRecord.timestamp >= (now - timedelta(days=30)).strftime("%Y-%m-%d"))
    return query

def attendance_stats(student: dict, all_records: list) -> dict:
    """Compute stats for one student from a pre-fetched record list."""
    roll  = student["roll_no"]
    sname = student["name"].lower()
    recs  = [r for r in all_records
             if (r.roll_no and r.roll_no == roll) or r.name.lower() == sname]
    total   = len(recs)
    present = sum(1 for r in recs if r.status == "present")
    pct     = round(present / total * 100) if total else 0
    return {
        **student,
        "photo_token":     photo_token(roll),
        "total_classes":   total,
        "present_count":   present,
        "attendance_pct":  pct,
        "below_threshold": total > 0 and pct < ATTENDANCE_THRESHOLD,
    }

# ── Page routes ───────────────────────────────────────────────────────
@app.route("/")
def login_page():    return render_template("login.html")

@app.route("/dashboard")
def dashboard():     return render_template("attendance.html")

@app.route("/students")
def students_page(): return render_template("students.html")

# ── Photo serving ─────────────────────────────────────────────────────
@app.route("/api/photo/<roll_no>")
def get_photo(roll_no):
    if request.args.get("t", "") != photo_token(roll_no):
        abort(403)
    student = find_student(load_students(), roll_no=roll_no)
    if student and os.path.exists(os.path.join(KNOWN_DIR, student["filename"])):
        resp = send_from_directory(KNOWN_DIR, student["filename"])
        resp.headers["Cache-Control"] = "public, max-age=3600"
        return resp
    abort(404)

# ── Auth ──────────────────────────────────────────────────────────────
@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json() or {}
    if data.get("username") == "admin" and data.get("password") == "1234":
        return jsonify({"token": create_access_token(identity="admin"), "user": "admin"})
    return jsonify({"error": "Invalid credentials"}), 401

# ── Subjects ──────────────────────────────────────────────────────────
@app.route("/api/subjects")
def get_subjects():
    if not authorized():
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(SUBJECTS)

# ── Students ──────────────────────────────────────────────────────────
@app.route("/api/students", methods=["GET", "POST"])
def handle_students():
    if not authorized():
        return jsonify({"error": "Unauthorized"}), 401

    if request.method == "POST":
        data    = request.get_json() or {}
        name    = (data.get("name")    or "").strip()
        roll    = (data.get("roll_no") or "").strip()
        photo   = data.get("photo", "")

        if not name or not roll or not photo:
            return jsonify({"error": "Name, roll number and photo are all required"}), 400

        students = load_students()
        if find_student(students, roll_no=roll):
            return jsonify({"error": f"Roll number {roll} already exists"}), 409

        try:
            img = decode_photo(photo)

            if FACE_RECOGNITION_AVAILABLE:
                if not face_recognition.face_encodings(np.array(img)):
                    return jsonify({"error": "No face detected — use a clear front-facing photo"}), 400

            filename = f"{name}_{roll}.jpg"
            img.save(os.path.join(KNOWN_DIR, filename), "JPEG", quality=95)

            students.append({
                "name":     name,
                "roll_no":  roll,
                "filename": filename,
                "added_on": datetime.now().isoformat(),
            })
            save_students(students)
            load_known_faces()
            return jsonify({"message": "Student registered successfully"})

        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # GET — fetch all records once, compute stats in Python
    students    = load_students()
    all_records = AttendanceRecord.query.all()   # single DB call
    return jsonify([attendance_stats(s, all_records) for s in students])

@app.route("/api/students/<roll_no>", methods=["DELETE"])
def delete_student(roll_no):
    if not authorized():
        return jsonify({"error": "Unauthorized"}), 401

    students = load_students()
    student  = find_student(students, roll_no=roll_no)
    if not student:
        return jsonify({"error": "Student not found"}), 404

    photo_path = os.path.join(KNOWN_DIR, student["filename"])
    if os.path.exists(photo_path):
        os.remove(photo_path)

    save_students([s for s in students if s["roll_no"] != roll_no])
    load_known_faces()
    return jsonify({"message": f"Deleted {student['name']}"})

# ── Attendance records ────────────────────────────────────────────────
@app.route("/api/full_records")
def full_records():
    if not authorized():
        return jsonify({"error": "Unauthorized"}), 401

    range_type = request.args.get("range", "all")
    subject    = request.args.get("subject", "")

    query = date_range_filter(AttendanceRecord.query, range_type)
    if subject and subject != "all":
        query = query.filter(AttendanceRecord.subject == subject)

    students_list = load_students()   # load once

    return jsonify([{
        "id":          r.id,
        "name":        r.name,
        "roll_no":     r.roll_no or "",
        "photo_token": photo_token(m["roll_no"]) if (m := find_student(
                           students_list, roll_no=r.roll_no or "", name=r.name
                       )) else "",
        "subject":     r.subject or "General",
        "date":        r.timestamp.split(" ")[0],
        "time":        r.timestamp.split(" ")[1] if " " in r.timestamp else "",
        "status":      r.status,
    } for r in query.order_by(AttendanceRecord.id.desc()).all()])

# ── Toggle record status ──────────────────────────────────────────────
@app.route("/api/records/<int:record_id>/toggle", methods=["POST"])
def toggle_record(record_id):
    if not authorized():
        return jsonify({"error": "Unauthorized"}), 401
    record = db.session.get(AttendanceRecord, record_id)
    if not record:
        return jsonify({"error": "Record not found"}), 404
    record.status = "absent" if record.status == "present" else "present"
    db.session.commit()
    return jsonify({"id": record.id, "status": record.status})

# ── Manual add record ─────────────────────────────────────────────────
@app.route("/api/records", methods=["POST"])
def add_record():
    if not authorized():
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Name is required"}), 400

    now = datetime.now()
    record = AttendanceRecord(
        name      = name,
        roll_no   = data.get("roll_no", ""),
        subject   = data.get("subject", "General"),
        timestamp = f"{data.get('date', now.strftime('%Y-%m-%d'))} {data.get('time', now.strftime('%H:%M:%S'))}",
        status    = data.get("status", "present"),
    )
    db.session.add(record)
    db.session.commit()
    return jsonify({"message": "Record added", "id": record.id})

# ── Detect (camera script) ────────────────────────────────────────────
@app.route("/api/detect", methods=["POST"])
def api_detect():
    if not authorized():
        return jsonify({"error": "Unauthorized"}), 401

    data    = request.get_json() or {}
    name    = (data.get("name") or "").strip()
    subject = data.get("subject", "General")
    if not name:
        return jsonify({"error": "Name required"}), 400

    today   = datetime.now().strftime("%Y-%m-%d")
    student = find_student(load_students(), name=name)
    roll_no = student["roll_no"] if student else ""

    if already_marked(roll_no, name, subject, today):
        return jsonify({"status": "duplicate", "message": f"{name} already marked for {subject} today"})

    record = AttendanceRecord(
        name      = student["name"] if student else name,
        roll_no   = roll_no,
        subject   = subject,
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        status    = "present",
    )
    db.session.add(record)
    db.session.commit()
    return jsonify({"status": "present", "name": name, "roll_no": roll_no, "id": record.id})

# ── Register face (camera script) ─────────────────────────────────────
@app.route("/api/register_face", methods=["POST"])
def register_face():
    if not authorized():
        return jsonify({"error": "Unauthorized"}), 401

    data    = request.get_json() or {}
    name    = (data.get("name")    or "").strip()
    roll_no = (data.get("roll_no") or "").strip()
    photos  = data.get("photos", [])

    if not name or not roll_no:
        return jsonify({"error": "Name and roll number are required"}), 400
    if not photos:
        return jsonify({"error": "At least one photo is required"}), 400

    students = load_students()
    if find_student(students, roll_no=roll_no):
        return jsonify({"error": f"Roll number {roll_no} already registered"}), 409

    saved_filename = None
    for idx, photo_data in enumerate(photos):
        try:
            img       = decode_photo(photo_data)
            img_array = np.array(img, dtype=np.uint8) if FACE_RECOGNITION_AVAILABLE else None

            if FACE_RECOGNITION_AVAILABLE:
                if not face_recognition.face_encodings(img_array):
                    continue   # no face — try next photo

            filename = f"{name}_{roll_no}.jpg"
            img.save(os.path.join(KNOWN_DIR, filename), "JPEG", quality=95)
            saved_filename = filename
            break              # use first valid photo

        except Exception as e:
            print(f"[register_face] photo {idx} error: {e}")

    if not saved_filename:
        return jsonify({"error": "No usable face found in any photo — try better lighting"}), 400

    students.append({
        "name":     name,
        "roll_no":  roll_no,
        "filename": saved_filename,
        "added_on": datetime.now().isoformat(),
    })
    save_students(students)
    load_known_faces()

    return jsonify({
        "message":     f"{name} registered successfully",
        "roll_no":     roll_no,
        "filename":    saved_filename,
        "photo_token": photo_token(roll_no),
        "known_count": len(known_names),
    })

# ── Mark absent (camera script end-of-session) ────────────────────────
@app.route("/api/mark_absent", methods=["POST"])
def mark_absent():
    if not authorized():
        return jsonify({"error": "Unauthorized"}), 401

    data          = request.get_json() or {}
    subject       = data.get("subject", "General")
    present_names = {n.lower() for n in data.get("present_names", [])}
    today         = datetime.now().strftime("%Y-%m-%d")
    marked_absent = []

    for student in load_students():
        if student["name"].lower() in present_names:
            continue
        if already_marked(student["roll_no"], student["name"], subject, today):
            continue
        db.session.add(AttendanceRecord(
            name      = student["name"],
            roll_no   = student["roll_no"],
            subject   = subject,
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            status    = "absent",
        ))
        marked_absent.append(student["name"])

    db.session.commit()
    return jsonify({"marked_absent": marked_absent, "count": len(marked_absent)})

# ── Reload faces (camera script) ──────────────────────────────────────
@app.route("/api/reload_faces", methods=["POST"])
def api_reload_faces():
    if not authorized():
        return jsonify({"error": "Unauthorized"}), 401
    load_known_faces()
    return jsonify({"message": "Reloaded", "known": len(known_names)})

# ── Status ────────────────────────────────────────────────────────────
@app.route("/api/status")
def api_status():
    today = datetime.now().strftime("%Y-%m-%d")
    return jsonify({
        "marked_today":   AttendanceRecord.query.filter(
                              AttendanceRecord.timestamp.startswith(today)
                          ).count(),
        "known_faces":    len(known_names),
        "total_students": len(load_students()),
        "subjects":       SUBJECTS,
        "threshold":      ATTENDANCE_THRESHOLD,
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)