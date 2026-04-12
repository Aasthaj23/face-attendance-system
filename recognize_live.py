import cv2
import face_recognition
import os
import numpy as np
from datetime import datetime
import time
import requests
from PIL import Image

# ── Settings ─────────────────────────────────────────────────────────
THRESHOLD            = 0.5        # stricter = fewer false matches
KNOWN_DIR            = "Known"
UNKNOWN_COOLDOWN_S   = 5
PROCESS_EVERY_N      = 2          # skip every other frame for speed
FLASK_URL            = "http://localhost:5000"
ANGLES_PER_PERSON    = 3          # photos taken during registration

os.makedirs(KNOWN_DIR, exist_ok=True)

# ── Load known faces ──────────────────────────────────────────────────
known_encodings: list = []
known_names:     list = []

def load_known_faces() -> None:
    known_encodings.clear()
    known_names.clear()
    print("--- Loading Known Faces ---")
    for filename in os.listdir(KNOWN_DIR):
        if not filename.lower().endswith((".jpg", ".jpeg", ".png")):
            continue
        path  = os.path.join(KNOWN_DIR, filename)
        name  = os.path.splitext(filename)[0].split("_")[0]
        image = cv2.imread(path)
        if image is None:
            continue
        rgb  = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        encs = face_recognition.face_encodings(rgb)
        if encs:
            known_encodings.append(encs[0])
            known_names.append(name)
            print(f"  ✅ {filename} → {name}")
    print(f"--- {len(known_names)} encoding(s) loaded ---")

load_known_faces()

# ── Mark attendance via Flask ─────────────────────────────────────────
marked = set()

def mark_attendance(name: str) -> None:
    if name in marked:
        return

    try:
        res = requests.post(
            f"{FLASK_URL}/api/detect",
            json={"name": name},
            timeout=2
        )

        if res.status_code != 200:
            print(f"[!] Server error: {res.status_code}")
            return

        data = res.json()
        status = data.get("status", "")

        if status != "error":
            marked.add(name)
            if status == "duplicate":
                print(f"[=] {name} already marked today")
            else:
                print(f"[+] {name} marked successfully")

    except requests.exceptions.ConnectionError:
        print("[!] Flask server not running")
    except Exception as e:
        print(f"[!] Error: {e}")
# ── Multi-angle registration ──────────────────────────────────────────
def register_new_person(video: cv2.VideoCapture) -> None:
    """
    Captures ANGLES_PER_PERSON photos of a new face.
    User slightly changes angle between each shot.
    """
    new_name = input("\nEnter name for this person: ").strip()
    if not new_name:
        print("[!] No name entered, skipping.")
        return

    print(f"\nRegistering '{new_name}' — {ANGLES_PER_PERSON} photos needed.")
    print("Slightly turn your head between each photo.\n")

    saved = 0
    for i in range(ANGLES_PER_PERSON):
        input(f"  → Press Enter for photo {i+1}/{ANGLES_PER_PERSON}...")
        ret, snap = video.read()
        if not ret:
            print("  [!] Could not capture frame.")
            continue

        # Verify a face exists in the snapshot before saving
        rgb  = cv2.cvtColor(snap, cv2.COLOR_BGR2RGB)
        encs = face_recognition.face_encodings(rgb)
        if not encs:
            print("  [!] No face detected — try again with better lighting.")
            continue

        filename = f"{new_name}_{i}_{int(time.time())}.jpg"
        cv2.imwrite(os.path.join(KNOWN_DIR, filename), snap)
        print(f"  ✅ Saved {filename}")
        saved += 1

    if saved > 0:
        load_known_faces()
        # Tell Flask to reload too
        try:
            requests.post(f"{FLASK_URL}/api/reload_faces", timeout=2)
            print(f"[+] Flask reloaded — {len(known_names)} face(s) in memory")
        except Exception:
            print("[!] Could not notify Flask — restart server.py to see new face")
    else:
        print("[!] No photos saved.")

# ── Registration state (unknown face popup) ───────────────────────────
class RegistrationState:
    def __init__(self):
        self.active    = False
        self.face_crop = None
        self._win      = "Unknown — press 's' to register, any key to dismiss"

    def start(self, crop: np.ndarray) -> None:
        if self.active:
            return
        self.face_crop = crop.copy()
        self.active    = True
        cv2.imshow(self._win, crop)

    def dismiss(self) -> None:
        try:
            cv2.destroyWindow(self._win)
        except Exception:
            pass
        self.active    = False
        self.face_crop = None

reg = RegistrationState()

# ── Smoothing: only confirm a name after N consecutive matches ─────────
CONFIRM_FRAMES   = 5
name_buffer:     list = []

def smooth_name(raw_name: str) -> str:
    """Return a confirmed name only after CONFIRM_FRAMES consecutive matches."""
    name_buffer.append(raw_name)
    if len(name_buffer) > CONFIRM_FRAMES:
        name_buffer.pop(0)
    if len(name_buffer) == CONFIRM_FRAMES and len(set(name_buffer)) == 1:
        return name_buffer[0]
    return ""   # not confirmed yet

# ── Camera loop ───────────────────────────────────────────────────────
video             = cv2.VideoCapture(0)
last_unknown_time = 0.0
prev_time         = time.time()
frame_count       = 0

# Store last known results so skipped frames still show boxes
last_results: list = []   # list of (top, right, bottom, left, name, confidence)

while True:
    ret, frame = video.read()
    if not ret:
        break

    # FPS
    now_time  = time.time()
    fps       = 1.0 / (now_time - prev_time) if (now_time - prev_time) > 0 else 0
    prev_time = now_time
    frame_count += 1

    # ── Process every Nth frame only ─────────────────────────────────
    if frame_count % PROCESS_EVERY_N == 0:
        small     = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
        rgb_small = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)

        locations = face_recognition.face_locations(rgb_small)
        encodings = face_recognition.face_encodings(rgb_small, locations)

        last_results = []

        for (top, right, bottom, left), enc in zip(locations, encodings):
            raw_name   = "Unknown"
            confidence = 0.0

            if known_encodings:
                distances = face_recognition.face_distance(known_encodings, enc)
                best      = int(np.argmin(distances))
                if distances[best] < THRESHOLD:
                    raw_name   = known_names[best]
                    confidence = round(1.0 - distances[best], 2)

            # Smooth — only confirm after consecutive frames
            confirmed = smooth_name(raw_name)
            if confirmed and confirmed != "Unknown":
                mark_attendance(confirmed)

            last_results.append((
                top*4, right*4, bottom*4, left*4,
                confirmed if confirmed else raw_name,
                confidence
            ))

    # ── Draw last known results on every frame ────────────────────────
    unknown_this_frame = False

    for (top, right, bottom, left, name, confidence) in last_results:
        color = (0, 200, 80) if name not in ("Unknown", "") else (0, 0, 220)

        cv2.rectangle(frame, (left, top - 30), (right, top), color, -1)
        label = f"{name} ({confidence})" if name not in ("Unknown", "") else "Unknown"
        cv2.putText(frame, label, (left + 5, top - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
        cv2.rectangle(frame, (left, top), (right, bottom), color, 2)

        if name in ("Unknown", ""):
            unknown_this_frame = True

    # ── Unknown face cooldown trigger ─────────────────────────────────
    if unknown_this_frame:
        detect_time = time.time()
        if detect_time - last_unknown_time > UNKNOWN_COOLDOWN_S and not reg.active:
            # Grab the first unknown face crop
            for (top, right, bottom, left, name, _) in last_results:
                if name in ("Unknown", ""):
                    crop = frame[top:bottom, left:right]
                    if crop.size > 0:
                        reg.start(crop)
                        last_unknown_time = detect_time
                        break

    # ── FPS overlay ───────────────────────────────────────────────────
    cv2.putText(frame, f"FPS: {int(fps)}", (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)
    cv2.putText(frame, f"Known: {len(known_names)}", (20, 70),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)

    cv2.imshow("Attendance System", frame)

    key = cv2.waitKey(1) & 0xFF
    if key == ord("q"):
        break
    elif key == ord("s") and reg.active:
        reg.dismiss()
        register_new_person(video)   # multi-angle registration
    elif reg.active:
        reg.dismiss()

video.release()
cv2.destroyAllWindows()