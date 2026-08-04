import os
import base64
import requests

FLASK_URL = "http://127.0.0.1:5000"
API_KEY   = "85ba7587e257e99ac59ad97a3e6c1ebfba1a0318ced994a895d4f9f13b28ce7d"
KNOWN_DIR = "Known"

headers = {"Content-Type": "application/json", "X-API-Key": API_KEY}

print("Waking server...")
try:
    r = requests.get(f"{FLASK_URL}/api/status", timeout=30)
    print(f"Server online — {r.json()}")
except Exception as e:
    print(f"Could not reach server: {e}")
    exit(1)

print("\nScanning Known/ folder...\n")

for filename in os.listdir(KNOWN_DIR):
    if not filename.lower().endswith((".jpg", ".jpeg", ".png")):
        continue

    stem = os.path.splitext(filename)[0]

    # Skip offline fallback files like "Name_ROLL_offline0.jpg"
    if "offline" in stem.lower():
        print(f"⏭  Skipping offline file: {filename}")
        continue

    if "_" not in stem:
        print(f"⏭  Skipping {filename} — expected format: FirstName LastName_ROLLNO.jpg")
        continue

    name, roll_no = stem.rsplit("_", 1)

    with open(os.path.join(KNOWN_DIR, filename), "rb") as f:
        photo_b64 = base64.b64encode(f.read()).decode("utf-8")

    print(f"Uploading: {name} ({roll_no})...", end=" ")

    try:
        res = requests.post(
            f"{FLASK_URL}/api/register_face",
            json    = {"name": name, "roll_no": roll_no, "photos": [photo_b64]},
            headers = headers,
            timeout = (5, 60)
        )

        if res.status_code == 200:
            print(f"✅ Registered!")
        elif res.status_code == 400:
            err = res.json().get("error", "")
            if "already registered" in err:
                print(f"⚠  Already on server (skipped)")
            else:
                print(f"❌ Rejected — {err}")
        elif res.status_code == 401:
            print("❌ Wrong API key — stopping.")
            break
        else:
            print(f"❌ Server error {res.status_code}: {res.text[:100]}")

    except requests.Timeout:
        print("❌ Timed out — server may be processing, try again")
    except requests.ConnectionError:
        print("❌ Connection lost")

print("\nDone! Check your dashboard Students page.")