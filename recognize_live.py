import cv2
import face_recognition
import os
import numpy as np
from datetime import datetime
import time
import requests

# ── Settings ─────────────────────────────────────────────────────────
THRESHOLD          = 0.5
KNOWN_DIR          = "Known"
UNKNOWN_COOLDOWN_S = 5
PROCESS_EVERY_N    = 2
ANGLES_PER_PERSON  = 3
CONFIRM_FRAMES     = 5
FLASK_URL          = "https://face-attendance-system-7nux.onrender.com"  # ← change this
API_KEY            = "85ba7587e257e99ac59ad97a3e6c1ebfba1a0318ced994a895d4f9f13b28ce7d"        # ← change this

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
            print(f"  ⚠ Could not read {filename}")
            continue
        rgb  = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        encs = face_recognition.face_encodings(rgb)
        if encs:
            known_encodings.append(encs[0])
            known_names.append(name)
            print(f"  ✅ {filename} → {name}")
        else:
            print(f"  ❌ No face found in {filename}")
    print(f"--- {len(known_names)} encoding(s) loaded ---\n")

load_known_faces()

# ── API helpers ───────────────────────────────────────────────────────
def api_headers() -> dict:
    return {
        "Content-Type": "application/json",
        "X-API-Key":    API_KEY      # FIX: always send API key
    }

# ── Mark attendance ───────────────────────────────────────────────────
marked       = set()   # marked today
failed_names = set()   # failed due to server down — retry later

def mark_attendance(name: str) -> None:
    if name in marked:
        return

    try:
        res  = requests.post(
            f"{FLASK_URL}/api/detect",
            json={"name": name},
            headers=api_headers(),
            timeout=3
        )
        data   = res.json()
        status = data.get("status", "")

        if res.status_code == 200:
            if status == "duplicate":
                marked.add(name)            # already marked — no need to retry
                print(f"[=] {name} already marked today")
            elif status in ("present", "late"):
                marked.add(name)
                failed_names.discard(name)  # clear from retry queue
                print(f"[+] {name} → {status}")
        else:
            print(f"[!] Server error {res.status_code} for {name}")
            failed_names.add(name)          # FIX: retry later

    except requests.exceptions.ConnectionError:
        print(f"[!] Server unreachable — will retry {name} when connection restored")
        failed_names.add(name)              # FIX: retry when server comes back
    except requests.exceptions.Timeout:
        print(f"[!] Request timed out for {name}")
        failed_names.add(name)
    except Exception as e:
        print(f"[!] Unexpected error: {e}")

def retry_failed() -> None:
    """Retry any names that failed due to server being down."""
    if not failed_names:
        return
    for name in list(failed_names):
        mark_attendance(name)

# ── Multi-angle registration ──────────────────────────────────────────
def register_new_person(video: cv2.VideoCapture) -> None:
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
        try:
            # FIX: send API key when notifying Flask
            requests.post(
                f"{FLASK_URL}/api/reload_faces",
                headers=api_headers(),
                timeout=3
            )
            print(f"[+] Flask notified — {len(known_names)} face(s) in memory")
        except Exception:
            print("[!] Could not notify Flask — it will reload on next restart")
    else:
        print("[!] No photos saved.")

# ── Registration state ────────────────────────────────────────────────
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

# ── Per-face smoothing buffer ─────────────────────────────────────────
# FIX: dict keyed by face position index — one buffer per face slot
# Using position index since faces shift between frames
face_buffers: dict = {}

def smooth_name(face_idx: int, raw_name: str) -> str:
    """
    Confirm a name only after CONFIRM_FRAMES consecutive matches
    for the same face slot. Each face in frame gets its own buffer.
    """
    buf = face_buffers.setdefault(face_idx, [])
    buf.append(raw_name)
    if len(buf) > CONFIRM_FRAMES:
        buf.pop(0)
    if len(buf) == CONFIRM_FRAMES and len(set(buf)) == 1:
        return buf[0]
    return ""

def clear_old_buffers(active_count: int) -> None:
    """Remove buffers for face slots no longer active."""
    for key in list(face_buffers.keys()):
        if key >= active_count:
            del face_buffers[key]

# ── Camera init ───────────────────────────────────────────────────────
video = cv2.VideoCapture(0)

# FIX: check camera opened successfully
if not video.isOpened():
    print("[ERROR] Could not open camera. Check your camera index.")
    exit(1)

print("[✓] Camera opened successfully")
print("[i] Press 'q' to quit, 's' to register unknown face\n")

last_unknown_time = 0.0
prev_time         = time.time()
frame_count       = 0
last_results: list = []
retry_counter      = 0   # retry failed marks every N frames

# ── Camera loop ───────────────────────────────────────────────────────
while True:
    ret, frame = video.read()
    if not ret:
        print("[!] Frame read failed — camera disconnected?")
        break

    now_time  = time.time()
    fps       = 1.0 / (now_time - prev_time) if (now_time - prev_time) > 0 else 0
    prev_time = now_time
    frame_count  += 1
    retry_counter += 1

    # Retry failed attendance marks every 300 frames (~10 seconds at 30fps)
    if retry_counter >= 300:
        retry_failed()
        retry_counter = 0

    # ── Process every Nth frame ───────────────────────────────────────
    if frame_count % PROCESS_EVERY_N == 0:
        small     = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
        rgb_small = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)

        locations = face_recognition.face_locations(rgb_small)
        encodings = face_recognition.face_encodings(rgb_small, locations)

        # Clear buffers for faces no longer in frame
        clear_old_buffers(len(locations))

        last_results = []

        for idx, ((top, right, bottom, left), enc) in enumerate(
            zip(locations, encodings)
        ):
            raw_name   = "Unknown"
            confidence = 0.0

            if known_encodings:
                distances = face_recognition.face_distance(known_encodings, enc)
                best      = int(np.argmin(distances))
                if distances[best] < THRESHOLD:
                    raw_name   = known_names[best]
                    confidence = round(1.0 - distances[best], 2)

            # FIX: pass face index so each face has its own buffer
            confirmed = smooth_name(idx, raw_name)

            if confirmed and confirmed != "Unknown":
                mark_attendance(confirmed)

            last_results.append((
                top*4, right*4, bottom*4, left*4,
                confirmed if confirmed else raw_name,
                confidence
            ))

    # ── Draw results ──────────────────────────────────────────────────
    unknown_this_frame = False

    for (top, right, bottom, left, name, confidence) in last_results:
        is_known = name not in ("Unknown", "")
        color    = (0, 200, 80) if is_known else (0, 0, 220)

        cv2.rectangle(frame, (left, top - 30), (right, top), color, -1)
        label = f"{name} ({confidence})" if is_known else "Unknown"
        cv2.putText(frame, label, (left + 5, top - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
        cv2.rectangle(frame, (left, top), (right, bottom), color, 2)

        if not is_known:
            unknown_this_frame = True

    # ── Unknown face popup ────────────────────────────────────────────
    if unknown_this_frame:
        detect_time = time.time()
        if detect_time - last_unknown_time > UNKNOWN_COOLDOWN_S and not reg.active:
            for (top, right, bottom, left, name, _) in last_results:
                if name in ("Unknown", ""):
                    crop = frame[top:bottom, left:right]
                    if crop.size > 0:
                        reg.start(crop)
                        last_unknown_time = detect_time
                        break

    # ── Overlays ──────────────────────────────────────────────────────
    cv2.putText(frame, f"FPS: {int(fps)}", (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)
    cv2.putText(frame, f"Known: {len(known_names)}", (20, 70),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
    cv2.putText(frame, f"Marked: {len(marked)}", (20, 95),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)

    if failed_names:
        cv2.putText(frame, f"Pending: {len(failed_names)}", (20, 120),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 165, 255), 1)

    cv2.imshow("Attendance System", frame)

    key = cv2.waitKey(1) & 0xFF
    if key == ord("q"):
        break
    elif key == ord("s") and reg.active:
        reg.dismiss()
        register_new_person(video)
    elif reg.active:
        reg.dismiss()

video.release()
cv2.destroyAllWindows()
print(f"\n[✓] Session ended. Total marked: {len(marked)}")
if failed_names:
    print(f"[!] These were not synced to server: {failed_names}")