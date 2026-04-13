import csv
import os
import numpy as np
from datetime import datetime, timedelta
from PIL import Image
from flask import Flask, render_template, request, redirect, jsonify
import sqlite3
from flask_cors import CORS
from flask_jwt_extended import (
    JWTManager,
    create_access_token,
    jwt_required,
    get_jwt_identity
)
import face_recognition

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
app = Flask(__name__)

app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY", "change-this-in-prod")
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=2)

jwt = JWTManager(app)
CORS(app)

KNOWN_DIR = "Known"
CSV_FILE = "attendance.csv"

os.makedirs(KNOWN_DIR, exist_ok=True)


if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, "w", newline="") as f:
        csv.writer(f).writerow(["Name", "Timestamp", "Status"])


known_encodings = []
known_names = []

def load_known_faces():
    known_encodings.clear()
    known_names.clear()

    print("Loading known faces...")

    for filename in os.listdir(KNOWN_DIR):
        if filename.lower().endswith((".jpg", ".png", ".jpeg")):
            path = os.path.join(KNOWN_DIR, filename)
            name = os.path.splitext(filename)[0]

            try:
                img = Image.open(path).convert("RGB")
                img_array = np.array(img)

                encodings = face_recognition.face_encodings(img_array)

                if encodings:
                    known_encodings.append(encodings[0])
                    known_names.append(name)
                    print(f"Loaded: {name}")
                else:
                    print(f"No face in {filename}")

            except Exception as e:
                print(f"Error loading {filename}: {e}")

load_known_faces()

def init_db():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        date TEXT,
        time TEXT
    )
    """)

    conn.commit()
    conn.close()

init_db()

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def already_marked_today(name):
    today = datetime.now().strftime("%Y-%m-%d")

    with open(CSV_FILE, "r") as f:
        for row in csv.DictReader(f):
            if row["Name"] == name and row["Timestamp"].startswith(today):
                return True
    return False


def write_attendance(name):
    now = datetime.now()
    cutoff = now.replace(hour=9, minute=10, second=0)

    status = "late" if now > cutoff else "present"

    with open(CSV_FILE, "a", newline="") as f:
        csv.writer(f).writerow([
            name,
            now.strftime("%Y-%m-%d %H:%M:%S"),
            status
        ])

    return status

# ─────────────────────────────────────────────
# AUTH (JWT)
# ─────────────────────────────────────────────
@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json()

    username = data.get("username")
    password = data.get("password")

    # ⚠️ Replace with DB in real production
    if username == "admin" and password == "1234":
        token = create_access_token(identity=username)
        return jsonify({
            "token": token,
            "user": username
        })

    return jsonify({"error": "Invalid credentials"}), 401


# ─────────────────────────────────────────────
# FRONTEND ROUTES
# ─────────────────────────────────────────────
@app.route("/")
def login_page():
    return render_template("login.html")


@app.route("/dashboard")
def dashboard():
    return render_template("attendance.html")


# ─────────────────────────────────────────────
# PROTECTED APIs
# ─────────────────────────────────────────────
@app.route("/api/detect", methods=["POST"])
@jwt_required()
def detect():
    data = request.get_json()

    name = data.get("name")

    if not name:
        return jsonify({"error": "No name provided"}), 400

    if already_marked_today(name):
        return jsonify({"message": "Already marked", "status": "duplicate"})

    status = write_attendance(name)

    return jsonify({
        "name": name,
        "status": status
    })


@app.route("/api/full_records")
@jwt_required()
def full_records():
    records = []

    try:
        with open(CSV_FILE, "r") as f:
            for row in csv.DictReader(f):
                dt = datetime.strptime(row["Timestamp"], "%Y-%m-%d %H:%M:%S")

                records.append({
                    "name": row["Name"],
                    "id": f"STU-{row['Name'][:3].upper()}",
                    "date": dt.strftime("%d-%m-%Y"),
                    "time": dt.strftime("%I:%M %p"),
                    "status": row["Status"]
                })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify(records[::-1])


@app.route("/api/status")
@jwt_required()
def status():
    today = datetime.now().strftime("%Y-%m-%d")
    count = 0

    with open(CSV_FILE, "r") as f:
        count = sum(
            1 for row in csv.DictReader(f)
            if row["Timestamp"].startswith(today)
        )

    return jsonify({
        "marked_today": count,
        "known_faces": len(known_names)
    })


@app.route("/api/reload_faces", methods=["POST"])
@jwt_required()
def reload_faces():
    load_known_faces()
    return jsonify({
        "loaded": len(known_names)
    })


# ─────────────────────────────────────────────
# RUN
# ─────────────────────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)