import cv2
import csv
import os
import numpy as np
import face_recognition
from datetime import datetime
from PIL import Image
from flask import Flask, render_template, request, redirect, session, jsonify
import sqlite3
from flask_cors import CORS
CORS(app)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-in-prod")


KNOWN_DIR = "Known"
CSV_FILE  = "attendance.csv"
THRESHOLD = 0.5


os.makedirs(KNOWN_DIR, exist_ok=True)


# ── Create CSV with headers if missing ──────────────────────────────
if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, "w", newline="") as f:
        csv.writer(f).writerow(["Name", "Timestamp", "Status"])


# ── Load known faces ─────────────────────────────────────────────────
known_encodings: list = []
known_names:     list = []


def load_known_faces() -> None:
    known_encodings.clear()
    known_names.clear()
    print("--- Loading Known Faces ---")
    for filename in os.listdir(KNOWN_DIR):
        if not filename.lower().endswith((".jpg", ".jpeg", ".png")):
            continue
        path = os.path.join(KNOWN_DIR, filename)
        name = os.path.splitext(filename)[0].split("_")[0]
        try:
            img       = Image.open(path).convert("RGB")
            img_array = np.array(img, dtype=np.uint8)
            # Optional debug: helps you spot bad images
            print(f"  → {filename} | shape: {img_array.shape}, dtype: {img_array.dtype}")
            encodings = face_recognition.face_encodings(img_array)
            if encodings:
                known_encodings.append(encodings[0])
                known_names.append(name)
                print(f"  ✅ {filename} → {name}")
            else:
                print(f"  ❌ No face in {filename}")
        except Exception as e:
            print(f"  ❌ Error loading {filename}: {e}")
    print(f"--- {len(known_names)} face(s) loaded ---")


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


# ── Helpers ──────────────────────────────────────────────────────────
def is_logged_in() -> bool:
    return session.get("user") is not None


def already_marked_today(name: str) -> bool:
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        with open(CSV_FILE, "r") as f:
            for row in csv.DictReader(f):
                if row["Name"] == name and row["Timestamp"].startswith(today):
                    return True
    except Exception:
        pass
    return False


def write_attendance(name: str) -> str:
    time_now = datetime.now()
    cutoff   = time_now.replace(hour=9, minute=10, second=0, microsecond=0)
    status   = "late" if time_now > cutoff else "present"
    with open(CSV_FILE, "a", newline="") as f:
        csv.writer(f).writerow([
            name,
            time_now.strftime("%Y-%m-%d %H:%M:%S"),
            status
        ])
    return status


# ── Auth ─────────────────────────────────────────────────────────────
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        if username == "admin" and password == "1234":
            session["user"] = username
            return redirect("/dashboard")
        return render_template("login.html", error="Invalid username or password")
    return render_template("login.html", error=None)


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# ── Dashboard ─────────────────────────────────────────────────────────
@app.route("/dashboard")
def dashboard():
    if not is_logged_in():
        return redirect("/")
    return render_template("attendance.html")


# ── API: mark attendance (CSV version) ────────────────────────────────
@app.route("/api/detect", methods=["POST"])
def detect():
    if not is_logged_in():
        return jsonify({"error": "Unauthorised"}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "No name provided"}), 400

    if already_marked_today(name):
        return jsonify({"message": "Already marked today", "status": "duplicate"}), 200

    status = write_attendance(name)
    print(f"[+] Marked: {name} ({status})")
    return jsonify({"status": status, "name": name}), 200


# ── API: full records ─────────────────────────────────────────────────
@app.route("/api/full_records")
def full_records():
    if not is_logged_in():
        return jsonify({"error": "Unauthorised"}), 401
    records = []
    try:
        with open(CSV_FILE, "r") as f:
            for row in csv.DictReader(f):
                try:
                    dt = datetime.strptime(row["Timestamp"], "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    continue
                records.append({
                    "name":   row["Name"],
                    "id":     f"STU-{row['Name'][:3].upper()}",
                    "date":   dt.strftime("%d-%m-%Y"),
                    "time":   dt.strftime("%I:%M %p"),
                    "status": row["Status"]
                })
    except Exception as e:
        print(f"[ERROR] {e}")
        return jsonify({"error": "Could not read records"}), 500
    return jsonify(records[::-1])


# ── API: reload faces ─────────────────────────────────────────────────
@app.route("/api/reload_faces", methods=["POST"])
def reload_faces():
    if not is_logged_in():
        return jsonify({"error": "Unauthorised"}), 401
    load_known_faces()
    return jsonify({"loaded": len(known_names), "names": known_names}), 200


# ── API: status ───────────────────────────────────────────────────────
@app.route("/api/status")
def status():
    if not is_logged_in():
        return jsonify({"error": "Unauthorised"}), 401
    today = datetime.now().strftime("%Y-%m-%d")
    count = 0
    try:
        with open(CSV_FILE, "r") as f:
            count = sum(
                1 for row in csv.DictReader(f)
                if row["Timestamp"].startswith(today)
            )
    except Exception:
        pass
    return jsonify({
        "marked_today": count,
        "known_faces":  len(known_names)
    })


# ── Run ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
       app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))