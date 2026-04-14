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

# Security Keys
app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY", "4cf445c9cf0a1de286c0b537e5dfcf1d8eeaff8a02380532c1e041c15127bc24")
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=2)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///attendance.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
jwt = JWTManager(app)
CORS(app)

# ── Settings ──────────────────────────────────────────────────────────
API_KEY = os.environ.get("API_KEY", "85ba7587e257e99ac59ad97a3e6c1ebfba1a0318ced994a895d4f9f13b28ce7d")
KNOWN_DIR = "Known"
STUDENTS_FILE = "students.json"

os.makedirs(KNOWN_DIR, exist_ok=True)

# ── Face recognition setup ────────────────
try:
    import face_recognition
    FACE_RECOGNITION_AVAILABLE = True
except ImportError:
    FACE_RECOGNITION_AVAILABLE = False

known_encodings = []
known_names = []

def load_known_faces():
    known_encodings.clear()
    known_names.clear()
    if not FACE_RECOGNITION_AVAILABLE: return
    
    for filename in os.listdir(KNOWN_DIR):
        if filename.lower().endswith((".jpg", ".jpeg", ".png")):
            path = os.path.join(KNOWN_DIR, filename)
            name = os.path.splitext(filename)[0].split("_")[0]
            try:
                img = Image.open(path).convert("RGB")
                img_array = np.array(img, dtype=np.uint8)
                encs = face_recognition.face_encodings(img_array)
                if encs:
                    known_encodings.append(encs[0])
                    known_names.append(name)
            except Exception as e:
                print(f"Error loading {filename}: {e}")

# Load faces on startup
load_known_faces()

# ── Models & Helpers ──────────────────────────────────────────────────
class AttendanceRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    timestamp = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), nullable=False)

with app.app_context():
    db.create_all()

def load_students():
    try:
        with open(STUDENTS_FILE, "r") as f: return json.load(f)
    except: return []

def save_students(students):
    with open(STUDENTS_FILE, "w") as f: json.dump(students, f, indent=2)

def is_jwt_valid():
    try:
        verify_jwt_in_request()
        return True
    except: return False

# ── API Routes ────────────────────────────────────────────────────────

@app.route("/")
def login_page(): return render_template("login.html")

@app.route("/dashboard")
def dashboard(): return render_template("attendance.html")

@app.route("/students")
def students_page():
    # If the user isn't logged in via JWT, send them to login
    return render_template("students.html")

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json() or {}
    if data.get("username") == "admin" and data.get("password") == "1234":
        token = create_access_token(identity="admin")
        return jsonify({"token": token, "user": "admin"})
    return jsonify({"error": "Invalid credentials"}), 401

@app.route("/api/students", methods=["GET", "POST"])
def handle_students():
    if not is_jwt_valid(): return jsonify({"error": "Unauthorized"}), 401
    
    if request.method == "POST":
        data = request.get_json() or {}
        name, roll, photo = data.get("name"), data.get("roll_no"), data.get("photo")
        
        if not name or not roll or not photo:
            return jsonify({"error": "Missing fields"}), 400
            
        try:
            header, encoded = photo.split(",", 1)
            img_bytes = base64.b64decode(encoded)
            img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
            
            # Verify face
            encs = face_recognition.face_encodings(np.array(img))
            if not encs: return jsonify({"error": "No face detected"}), 400
            
            filename = f"{name}_{roll}.jpg"
            img.save(os.path.join(KNOWN_DIR, filename), "JPEG")
            
            students = load_students()
            students.append({"name": name, "roll_no": roll, "filename": filename, "added_on": datetime.now().isoformat()})
            save_students(students)
            load_known_faces()
            return jsonify({"message": "Success"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
            
    return jsonify(load_students())

@app.route("/api/students/<roll_no>", methods=["DELETE"])
def delete_student(roll_no):
    if not is_jwt_valid(): return jsonify({"error": "Unauthorized"}), 401
    students = load_students()
    student = next((s for s in students if s["roll_no"] == roll_no), None)
    if student:
        path = os.path.join(KNOWN_DIR, student["filename"])
        if os.path.exists(path): os.remove(path)
        students = [s for s in students if s["roll_no"] != roll_no]
        save_students(students)
        load_known_faces()
        return jsonify({"message": "Deleted"})
    return jsonify({"error": "Not found"}), 404

@app.route("/api/full_records")
def full_records():
    # Use standard headers check
    rows = AttendanceRecord.query.order_by(AttendanceRecord.id.desc()).all()
    records = []
    for r in rows:
        records.append({
            "name": r.name,
            "id": f"STU-{r.name[:3].upper()}",
            "date": r.timestamp.split(" ")[0],
            "time": r.timestamp.split(" ")[1],
            "status": r.status
        })
    return jsonify(records)

@app.route("/api/status")
def api_status():
    today = datetime.now().strftime("%Y-%m-%d")
    count = AttendanceRecord.query.filter(AttendanceRecord.timestamp.startswith(today)).count()
    return jsonify({
        "marked_today": count,
        "known_faces": len(known_names),
        "total_students": len(load_students())
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)