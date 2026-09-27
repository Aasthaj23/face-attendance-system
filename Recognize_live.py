"""
Attendance camera client — large hall / single camera edition
================================================================
ARCHITECTURE (important):
  This script runs on a LOCAL machine that has the physical camera
  attached (a PC, mini-PC, or NUC in the hall — NOT Render or any
  cloud host). It does capture + face detection + recognition here,
  then POSTs only small JSON attendance results to your Flask API
  (which can live on Render's free tier, since that side is just
  request/response, not video processing).

  Render's free tier CANNOT run cv2.imshow() or read a camera device
  directly — it has no display and no attached hardware. Keep the
  server (app.py / Flask) separate from this client, exactly as your
  original project already split them. This file only replaces the
  camera-side script.

DISTANCE REALITY:
  At 10-15m, even with a 4K camera, recognition confidence will be
  noticeably lower than at 3-5m, especially for anyone not looking
  roughly at the camera. This script biases toward fewer false
  positives (longer confirmation, tighter threshold) rather than
  fast recognition, which matters more at range.
"""

import cv2
import face_recognition
import os
import numpy as np
import time
import base64
import json
import requests
from datetime import datetime
from requests.exceptions import ConnectionError, Timeout, RequestException
from services import face_service
from services.liveness_service import LIVENESS_CHALLENGE, LivenessTracker

# ── Settings ─────────────────────────────────────────────────────────
THRESHOLD           = 0.5
KNOWN_DIR           = "Known"
UNKNOWN_COOLDOWN_S  = 5
ANGLES_PER_PERSON   = 3
CONFIRM_FRAMES      = 7          # higher than before — range needs more confirmation, not less
FLASK_URL           = "http://127.0.0.1:5000"
API_KEY             = os.environ["API_KEY"]

# Camera capture resolution. Request the highest your camera supports.
# A webcam that maxes out at 1080p will simply ignore the 4K request
# and fall back to its native max — that's fine, just know your ceiling.
CAPTURE_WIDTH       = 3840
CAPTURE_HEIGHT      = 2160

# Detection frame target width. Face detection runs on a resized copy
# of the frame for speed — but unlike a close-range webcam setup, we
# can't blindly shrink to 25%: at 10-15m the face is already small in
# absolute pixels, so over-shrinking destroys the encoding. This picks
# a resize factor that keeps the detection frame at ~DETECT_TARGET_W,
# whatever the source resolution actually is.
DETECT_TARGET_W     = 1280
PROCESS_EVERY_N      = 2

# Face tracker: how far (in detection-frame pixels) a face centroid
# can move between processed frames and still be considered "the same
# face" — not "the same index in the list" like the original script.
TRACK_MAX_DIST_PX   = 60
TRACK_MAX_MISSES    = 6          # frames a tracked face can go undetected before being dropped

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
        path = os.path.join(KNOWN_DIR, filename)
        stem = os.path.splitext(filename)[0]
        name = stem.rsplit("_", 1)[0] if "_" in stem else stem

        image = cv2.imread(path)
        if image is None:
            print(f"  \u26a0 Could not read {filename}")
            continue

        rgb  = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        encs = face_recognition.face_encodings(rgb)
        if encs:
            known_encodings.append(encs[0])
            known_names.append(name)
            print(f"  \u2705 {filename}  \u2192  '{name}'")
        else:
            print(f"  \u274c No face in {filename}")

    face_service.known_encodings[:] = known_encodings
    face_service.known_names[:] = known_names
    face_service.known_student_ids[:] = [None] * len(known_names)
    print(f"--- {len(known_names)} face(s) loaded ---\n")

load_known_faces()
face_service.known_encodings[:] = known_encodings
face_service.known_names[:] = known_names
face_service.known_student_ids[:] = [None] * len(known_names)

# ── API helpers ───────────────────────────────────────────────────────
def api_headers() -> dict:
    return {"Content-Type": "application/json", "X-API-Key": API_KEY}

def safe_json(res: requests.Response):
    try:
        return res.json(), None
    except Exception as e:
        preview = (res.text or "")[:200]
        return None, f"Invalid JSON (HTTP {res.status_code}): {e} — {preview}"

# ── Attendance marking ────────────────────────────────────────────────
marked       = set()
failed_names = set()

def mark_attendance(name: str) -> None:
    if name in marked:
        return
    try:
        res = requests.post(f"{FLASK_URL}/api/detect", json={"name": name},
                             headers=api_headers(), timeout=(3, 5))
        data, err = safe_json(res)
        if err:
            print(f"[!] {name}: {err}")
            failed_names.add(name)
            return
        status = (data or {}).get("status", "")
        if res.status_code == 200:
            if status in ("present", "late", "duplicate"):
                marked.add(name)
                failed_names.discard(name)
                icon = "=" if status == "duplicate" else "+"
                print(f"[{icon}] {name} \u2192 {status}")
            else:
                print(f"[!] Unexpected response for {name}: {data}")
                failed_names.add(name)
        elif res.status_code == 401:
            print("[!] Unauthorized — check API_KEY")
            failed_names.add(name)
        else:
            print(f"[!] Server error {res.status_code} for {name}: {data}")
            failed_names.add(name)
    except ConnectionError:
        print(f"[!] Server unreachable — queuing {name} for retry")
        failed_names.add(name)
    except Timeout:
        print(f"[!] Timeout for {name} — queuing for retry")
        failed_names.add(name)
    except RequestException as e:
        print(f"[!] Request error for {name}: {e}")
        failed_names.add(name)

def retry_failed() -> None:
    if not failed_names:
        return
    print(f"[i] Retrying {len(failed_names)} pending record(s)...")
    for name in list(failed_names):
        mark_attendance(name)

def frame_to_base64(frame: np.ndarray) -> str:
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        raise ValueError("Could not encode frame as JPEG")
    return base64.b64encode(buf.tobytes()).decode("utf-8")

# ── Registration (unchanged logic, still works for a hall setup) ──────
def register_new_person(video: cv2.VideoCapture) -> None:
    print("\n" + "─" * 50)
    new_name = input("Enter student's FULL NAME  (e.g. Aastha Jain): ").strip()
    if not new_name:
        print("[!] No name entered — skipping registration.")
        return
    roll_no = input("Enter ROLL NUMBER           (e.g. CSE2301):     ").strip()
    if not roll_no:
        print("[!] No roll number entered — skipping registration.")
        return

    print(f"\nCapturing {ANGLES_PER_PERSON} photos of '{new_name}' (roll: {roll_no}).")
    print("For a hall camera, have the student walk up close for registration —")
    print("registering from 10-15m away will produce a poor-quality encoding.\n")

    captured_frames = []
    for i in range(ANGLES_PER_PERSON):
        input(f"  \u2192 Press Enter for photo {i+1}/{ANGLES_PER_PERSON}...")
        for _ in range(3):
            video.grab()
        ret, snap = video.read()
        if not ret or snap is None:
            print("  [!] Could not capture frame — skipping this shot.")
            continue
        rgb  = cv2.cvtColor(snap, cv2.COLOR_BGR2RGB)
        locs = face_recognition.face_locations(rgb)
        if not locs:
            print("  [!] No face detected in this photo. Move closer / improve lighting.")
            continue
        captured_frames.append(snap)
        print(f"  \u2705 Photo {i+1} captured ({len(locs)} face(s) detected)")

    if not captured_frames:
        print("[!] No usable photos captured — registration cancelled.")
        return

    print(f"\n[\u2192] Encoding {len(captured_frames)} photo(s) and sending to server...")
    photos_b64 = []
    for frame in captured_frames:
        try:
            photos_b64.append(frame_to_base64(frame))
        except Exception as e:
            print(f"  [!] Encoding failed for one frame: {e}")

    if not photos_b64:
        print("[!] All encoding attempts failed — registration cancelled.")
        return

    try:
        res = requests.post(f"{FLASK_URL}/api/register_face",
                             json={"name": new_name, "roll_no": roll_no, "photos": photos_b64},
                             headers=api_headers(), timeout=(5, 30))
        data, err = safe_json(res)
        if err:
            print(f"[!] Server returned invalid response: {err}")
            _save_locally_fallback(new_name, roll_no, captured_frames)
            return
        if res.status_code == 200:
            print(f"\n[\u2713] '{new_name}' (roll: {roll_no}) registered on server!")
            print(f"    Server now has {data.get('known_count', '?')} known face(s).")
            _save_best_locally(new_name, roll_no, captured_frames)
            load_known_faces()
        elif res.status_code == 400:
            print(f"[!] Registration rejected: {(data or {}).get('error', 'Unknown reason')}")
        elif res.status_code == 401:
            print("[!] Server rejected API key — check API_KEY in settings.")
            _save_locally_fallback(new_name, roll_no, captured_frames)
        else:
            print(f"[!] Server error {res.status_code}: {data}")
            _save_locally_fallback(new_name, roll_no, captured_frames)
    except ConnectionError:
        print("[!] Server unreachable — saving locally for now.")
        _save_locally_fallback(new_name, roll_no, captured_frames)
    except Timeout:
        print("[!] Server timed out — saving locally for now.")
        _save_locally_fallback(new_name, roll_no, captured_frames)
    except RequestException as e:
        print(f"[!] Request error: {e} — saving locally for now.")
        _save_locally_fallback(new_name, roll_no, captured_frames)

    print("─" * 50 + "\n")

def _save_best_locally(name: str, roll_no: str, frames: list) -> None:
    filename = f"{name}_{roll_no}.jpg"
    path     = os.path.join(KNOWN_DIR, filename)
    if not os.path.exists(path):
        cv2.imwrite(path, frames[0])
        print(f"    Saved locally: {filename}")

def _save_locally_fallback(name: str, roll_no: str, frames: list) -> None:
    saved = 0
    for i, frame in enumerate(frames):
        filename = f"{name}_{roll_no}_offline{i}.jpg"
        path     = os.path.join(KNOWN_DIR, filename)
        cv2.imwrite(path, frame)
        saved += 1
    if saved:
        load_known_faces()
        print(f"[i] Saved {saved} photo(s) locally to Known/.")
        print(f"[i] '{name}' will be recognised in this session.")
        print("[!] They will NOT appear in the dashboard until the server is online.")

def close_session(subject: str = "General") -> None:
    if not marked:
        print("[i] No one was marked present — skipping absent marking.")
        return
    print(f"\n[\u2192] Marking absent students for subject: {subject}...")
    try:
        res = requests.post(f"{FLASK_URL}/api/mark_absent",
                             json={"subject": subject, "present_names": list(marked)},
                             headers=api_headers(), timeout=(5, 15))
        data, err = safe_json(res)
        if err:
            print(f"[!] Could not mark absents: {err}")
        elif res.ok:
            absent_list = (data or {}).get("marked_absent", [])
            print(f"[\u2713] Marked {len(absent_list)} student(s) absent: {absent_list}")
        else:
            print(f"[!] Server error marking absents: {data}")
    except Exception as e:
        print(f"[!] Failed to mark absents: {e}")

# ── Registration popup state ───────────────────────────────────────────
class RegistrationState:
    WIN = "Unknown face — press S to register, any other key to dismiss"

    def __init__(self):
        self.active    = False
        self.face_crop = None

    def start(self, crop: np.ndarray) -> None:
        if self.active:
            return
        self.face_crop = crop.copy()
        self.active    = True
        cv2.imshow(self.WIN, crop)

    def dismiss(self) -> None:
        try:
            cv2.destroyWindow(self.WIN)
        except Exception:
            pass
        self.active    = False
        self.face_crop = None

reg = RegistrationState()

# ── Stable face tracker (replaces index-based smoothing) ───────────────
# The original script assumed the Nth face detected this frame is the
# same physical person as the Nth face detected last frame. In a full
# hall with many faces, detection order is not stable — this caused
# names to flicker and never reach CONFIRM_FRAMES. Instead, we match
# faces between frames by nearest centroid, so each tracked face keeps
# its own identity and vote history as it moves.
class Track:
    __slots__ = ("centroid", "box", "votes", "misses", "confirmed_name", "live")

    def __init__(self, centroid, box):
        self.centroid = centroid
        self.box = box
        self.votes = []
        self.misses = 0
        self.confirmed_name = ""
        self.live = False

    def vote(self, raw_name: str) -> None:
        self.votes.append(raw_name)
        if len(self.votes) > CONFIRM_FRAMES:
            self.votes.pop(0)
        if len(self.votes) == CONFIRM_FRAMES and len(set(self.votes)) == 1:
            self.confirmed_name = self.votes[0]

tracks: list = []
liveness_tracker = LivenessTracker()

def update_tracks(detections):
    """
    detections: list of (centroid_xy, box, raw_name, is_live)
    Greedy nearest-centroid matching against existing tracks.
    """
    global tracks
    unmatched_tracks = list(range(len(tracks)))
    unmatched_dets   = list(range(len(detections)))
    matches = []

    for ti in list(unmatched_tracks):
        best_di, best_dist = None, None
        for di in unmatched_dets:
            cx, cy = detections[di][0]
            tx, ty = tracks[ti].centroid
            dist = ((cx - tx) ** 2 + (cy - ty) ** 2) ** 0.5
            if best_dist is None or dist < best_dist:
                best_dist, best_di = dist, di
        if best_di is not None and best_dist <= TRACK_MAX_DIST_PX:
            matches.append((ti, best_di))
            unmatched_tracks.remove(ti)
            unmatched_dets.remove(best_di)

    for ti, di in matches:
        centroid, box, raw_name, is_live = detections[di]
        tracks[ti].centroid = centroid
        tracks[ti].box = box
        tracks[ti].misses = 0
        tracks[ti].live = is_live
        if is_live:
            tracks[ti].vote(raw_name)

    for ti in unmatched_tracks:
        tracks[ti].misses += 1

    for di in unmatched_dets:
        centroid, box, raw_name, is_live = detections[di]
        t = Track(centroid, box)
        t.live = is_live
        if is_live:
            t.vote(raw_name)
        tracks.append(t)

    tracks = [t for t in tracks if t.misses <= TRACK_MAX_MISSES]

# ── Camera init ───────────────────────────────────────────────────────
video = cv2.VideoCapture(0)
video.set(cv2.CAP_PROP_FRAME_WIDTH, CAPTURE_WIDTH)
video.set(cv2.CAP_PROP_FRAME_HEIGHT, CAPTURE_HEIGHT)
if not video.isOpened():
    print("[ERROR] Could not open camera. Check your camera index (try 1 or 2).")
    raise SystemExit(1)

actual_w = int(video.get(cv2.CAP_PROP_FRAME_WIDTH))
actual_h = int(video.get(cv2.CAP_PROP_FRAME_HEIGHT))
print(f"[\u2713] Camera opened at {actual_w}x{actual_h}")
if actual_w < 1920:
    print("[!] Warning: camera max resolution is below 1080p.")
    print("    At 10-15m range this will significantly limit recognition")
    print("    accuracy, especially for anyone not near the camera axis.")
print("[i] Controls:  Q = quit   S = register unknown face\n")

# Resize factor computed from the ACTUAL camera resolution, not hardcoded.
resize_factor = min(1.0, DETECT_TARGET_W / max(actual_w, 1))

last_unknown_time = 0.0
prev_time         = time.time()
frame_count       = 0
retry_counter     = 0

while True:
    ret, frame = video.read()
    if not ret:
        print("[!] Frame read failed — camera disconnected?")
        break

    now_t     = time.time()
    fps       = 1.0 / max(now_t - prev_time, 1e-6)
    prev_time = now_t
    frame_count   += 1
    retry_counter += 1

    if retry_counter >= 300:
        retry_failed()
        retry_counter = 0

    if frame_count % PROCESS_EVERY_N == 0:
        if resize_factor < 1.0:
            small = cv2.resize(frame, (0, 0), fx=resize_factor, fy=resize_factor)
        else:
            small = frame
        rgb_small = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)

        locations = face_recognition.face_locations(rgb_small)
        landmarks = face_recognition.face_landmarks(rgb_small, locations)
        live_faces = [
            liveness_tracker.update(
                ((left + right) / 2.0, (top + bottom) / 2.0),
                face_landmarks,
            )
            for (top, right, bottom, left), face_landmarks in zip(locations, landmarks)
        ]
        detections = []
        for index, ((top, right, bottom, left), is_live) in enumerate(zip(locations, live_faces)):
            raw_name = "Unknown"
            if is_live:
                encodings = face_recognition.face_encodings(rgb_small, [locations[index]])
                if encodings:
                    raw_name, _ = face_service.recognize_face(encodings[0])
                    raw_name = raw_name or "Unknown"
            centroid = ((left + right) / 2.0, (top + bottom) / 2.0)
            detections.append((centroid, (top, right, bottom, left), raw_name, is_live))

        update_tracks(detections)

        for t in tracks:
            if t.live and t.confirmed_name and t.confirmed_name != "Unknown":
                mark_attendance(t.confirmed_name)

    inv_scale = 1.0 / resize_factor if resize_factor > 0 else 1.0
    unknown_in_frame = False

    for t in tracks:
        if t.misses > 0:
            continue
        top, right, bottom, left = [int(v * inv_scale) for v in t.box]
        name = t.confirmed_name if t.confirmed_name else "Unknown"
        is_known = name != "Unknown"
        color = (0, 200, 80) if is_known else (0, 0, 220)

        cv2.rectangle(frame, (left, top - 32), (right, top), color, cv2.FILLED)
        cv2.putText(frame, name, (left + 5, top - 9),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.52, (255, 255, 255), 1, cv2.LINE_AA)
        cv2.rectangle(frame, (left, top), (right, bottom), color, 2)

        if not is_known:
            unknown_in_frame = True
            crop_box = (top, right, bottom, left)

    if unknown_in_frame:
        detect_time = time.time()
        if detect_time - last_unknown_time > UNKNOWN_COOLDOWN_S and not reg.active:
            top, right, bottom, left = crop_box
            crop = frame[max(top, 0):bottom, max(left, 0):right]
            if crop.size > 0:
                reg.start(crop)
                last_unknown_time = detect_time

    hud_lines = [
        (LIVENESS_CHALLENGE,       (0, 220, 255), 0.58, 1),
        (f"FPS: {int(fps)}",           (255, 255,   0), 0.75, 2),
        (f"Res: {actual_w}x{actual_h}", (200, 200, 200), 0.55, 1),
        (f"Known: {len(known_names)}", (200, 200, 200), 0.58, 1),
        (f"Marked: {len(marked)}",     (200, 200, 200), 0.58, 1),
    ]
    if failed_names:
        hud_lines.append((f"Pending: {len(failed_names)}", (0, 165, 255), 0.58, 1))

    y = 38
    for text, color, scale, thickness in hud_lines:
        cv2.putText(frame, text, (18, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness, cv2.LINE_AA)
        y += 28

    display = frame if actual_w <= 1600 else cv2.resize(frame, (0, 0), fx=1600 / actual_w, fy=1600 / actual_w)
    cv2.imshow("Attendance System  |  Q=quit  S=register unknown", display)

    key = cv2.waitKey(1) & 0xFF
    if key == ord("q"):
        break
    elif key == ord("s"):
        if reg.active:
            reg.dismiss()
        register_new_person(video)
    elif reg.active:
        reg.dismiss()

video.release()
cv2.destroyAllWindows()

print(f"\n[\u2713] Session ended — {len(marked)} student(s) marked present.")

print("\nWhich subject was this session for?")
for i, subj in enumerate(["Mathematics", "Physics", "Chemistry",
                           "Computer Science", "English", "Physical Education"]):
    print(f"  {i+1}. {subj}")

choice = input("Enter number (or press Enter to skip absent marking): ").strip()
subject_map = {"1": "Mathematics", "2": "Physics", "3": "Chemistry",
               "4": "Computer Science", "5": "English", "6": "Physical Education"}
chosen_subject = subject_map.get(choice)

if chosen_subject:
    close_session(subject=chosen_subject)
else:
    print("[i] Skipped absent marking.")

if failed_names:
    print(f"[!] These were NOT synced to server: {failed_names}")
    print("    Re-run the script when the server is online to retry.")