"""
BetVibe Backend Server
=====================
Runs on Railway / Render (or locally).

Endpoints:
  GET  /matches.json
  POST /api/run-scraper
  GET  /api/scraper-status
  POST /api/can-place-bet       ← NEW
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
from functools import wraps
import threading
import subprocess
import time
import os
import json
from datetime import datetime, timezone, timedelta

# ── NEW: zoneinfo for IST ─────────────────────
try:
    from zoneinfo import ZoneInfo          # Python 3.9+
except ImportError:
    from backports.zoneinfo import ZoneInfo  # Python 3.8 fallback

IST = ZoneInfo("Asia/Kolkata")

# ── CONFIG ───────────────────────────────────
ADMIN_KEY = "betvibe@2025"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("PORT", 5000))

scraper_status = {
    "running": False,
    "last_run": None,
    "last_result": "Never run",
    "error": None
}

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})


# ── AUTH ─────────────────────────────────────
def require_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get("X-Admin-Key") or request.args.get("key")
        if key != ADMIN_KEY:
            return jsonify({"ok": False, "msg": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


# ── NEW HELPER ────────────────────────────────
def load_matches():
    """Safely load matches.json from BASE_DIR. Returns list or []."""
    path = os.path.join(BASE_DIR, "matches.json")
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ── ROUTES ───────────────────────────────────
@app.route("/")
def home():
    return jsonify({
        "status": "BetVibe backend running",
        "endpoints": [
            "/matches.json",
            "/api/run-scraper",
            "/api/scraper-status",
            "/api/can-place-bet"
        ]
    })


@app.route("/matches.json")
def matches():
    path = os.path.join(BASE_DIR, "matches.json")

    if not os.path.exists(path):
        return jsonify([])

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return jsonify(data)


@app.route("/api/run-scraper", methods=["POST"])
@require_key
def trigger_scraper():
    if scraper_status["running"]:
        return jsonify({
            "ok": False,
            "msg": "Scraper already running"
        }), 409

    threading.Thread(target=run_scraper_task, daemon=True).start()

    return jsonify({
        "ok": True,
        "msg": "Scraper started"
    })


@app.route("/api/scraper-status")
@require_key
def scraper_status_api():
    return jsonify(scraper_status)


# ── NEW ROUTE: /api/can-place-bet ─────────────
@app.route("/api/can-place-bet", methods=["POST"])
def can_place_bet():
    """
    Input  JSON: { "match": "GT vs MI" }
    Logic:
      - Find the match row in matches.json by match or match_link_text field.
      - Parse date_ist + time_ist to a timezone-aware IST datetime.
      - Toss market closes exactly 60 minutes before match_time.
      - Return ok=true if current IST time < close_time, else ok=false.
    """
    body = request.get_json(silent=True) or {}
    match_name = (body.get("match") or "").strip()

    if not match_name:
        return jsonify({"ok": False, "msg": "match field required"}), 400

    # ── 1. Load matches ──────────────────────
    try:
        all_matches = load_matches()
    except Exception as e:
        return jsonify({"ok": False, "msg": f"Could not load matches: {e}"}), 500

    # ── 2. Find the requested match ──────────
    row = None
    for m in all_matches:
        if (m.get("match") == match_name or
                m.get("match_link_text") == match_name):
            row = m
            break

    if row is None:
        return jsonify({"ok": False, "msg": "Match not found"}), 404

    # ── 3. Parse match datetime (IST) ────────
    date_str = (row.get("date_ist") or "").strip()
    time_str = (row.get("time_ist") or "").strip()

    if not date_str or not time_str:
        return jsonify({"ok": False, "msg": "Invalid match time"}), 400

    try:
        # Expected format: date_ist = "19-04-2026", time_ist = "03:30 PM"
        match_naive = datetime.strptime(
            f"{date_str} {time_str}", "%d-%m-%Y %I:%M %p"
        )
        match_time = match_naive.replace(tzinfo=IST)
    except ValueError:
        return jsonify({"ok": False, "msg": "Invalid match time"}), 400

    # ── 4. Compute close time (60 min before match) ──
    close_time = match_time - timedelta(minutes=60)
    now_ist = datetime.now(IST)

    close_time_str = close_time.strftime("%d %b %Y %I:%M %p IST")
    match_time_str = match_time.strftime("%d %b %Y %I:%M %p IST")

    # ── 5. Decision ──────────────────────────
    if now_ist >= close_time:
        return jsonify({
            "ok": False,
            "msg": "Toss market closed",
            "close_time": close_time_str,
            "match_time": match_time_str
        })

    return jsonify({
        "ok": True,
        "msg": "Bet allowed",
        "close_time": close_time_str,
        "match_time": match_time_str
    })


# ── SCRAPER ──────────────────────────────────
def run_scraper_task():
    scraper_status["running"] = True
    scraper_status["error"] = None

    try:
        result = subprocess.run(
            ["python3", os.path.join(BASE_DIR, "Match_details.py")],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=BASE_DIR
        )

        scraper_status["last_result"] = (result.stdout or "Done")[-600:]

        if result.returncode != 0:
            scraper_status["error"] = (result.stderr or "Unknown error")[-400:]

    except subprocess.TimeoutExpired:
        scraper_status["error"] = "Timed out after 5 minutes."

    except Exception as e:
        scraper_status["error"] = str(e)
        scraper_status["last_result"] = "Failed"

    finally:
        scraper_status["running"] = False

        ist = timezone(timedelta(hours=5, minutes=30))
        scraper_status["last_run"] = datetime.now(ist).strftime(
            "%d %b %Y %I:%M %p IST"
        )


# ── AUTO UPDATE ──────────────────────────────
def auto_updater():
    time.sleep(15)

    while True:
        if not scraper_status["running"]:
            run_scraper_task()

        time.sleep(1800)   # every 30 min


# Start background updater for Railway/Gunicorn
threading.Thread(target=auto_updater, daemon=True).start()


# ── START APP ────────────────────────────────
if __name__ == "__main__":
    print(f"BetVibe running on port {PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
