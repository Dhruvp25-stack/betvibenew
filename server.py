"""
BetVibe Backend Server
=====================
Runs on Railway / Render (or locally).

Endpoints:
  GET  /matches.json
  POST /api/run-scraper
  GET  /api/scraper-status
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
from functools import wraps
import threading
import subprocess
import time
import os
from datetime import datetime, timezone, timedelta

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


# ── ROUTES ───────────────────────────────────
@app.route("/")
def home():
    return jsonify({
        "status": "BetVibe backend running",
        "endpoints": [
            "/matches.json",
            "/api/run-scraper",
            "/api/scraper-status"
        ]
    })


@app.route("/matches.json")
def matches():
    path = os.path.join(BASE_DIR, "matches.json")

    if not os.path.exists(path):
        return jsonify([])

    import json
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