"""
BetVibe Backend Server
======================
Flask + Flask-SocketIO for real-time push updates.
Runs on Railway / Render with gunicorn + eventlet.

Endpoints:
  GET  /matches.json
  GET  /api/matches          ← with status filter ?status=live|upcoming|completed
  POST /api/run-scraper
  GET  /api/scraper-status
  POST /api/can-place-bet
  GET  /api/health

WebSocket events (Socket.IO):
  server → client: 'matches_update'   payload: {matches, counts}
  server → client: 'scraper_done'     payload: {status, time}
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

# ── Real-time via Flask-SocketIO ─────────────────────────────────────
try:
    from flask_socketio import SocketIO, emit
    HAS_SOCKETIO = True
except ImportError:
    HAS_SOCKETIO = False
    print("[WARN] flask-socketio not installed – real-time disabled")

# ── IST timezone ─────────────────────────────────────────────────────
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

# ── CONFIG ────────────────────────────────────────────────────────────
ADMIN_KEY = os.environ.get("ADMIN_KEY", "betvibe@2025")
BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
PORT      = int(os.environ.get("PORT", 5000))
AUTO_REFRESH_INTERVAL = 1800   # 30 minutes

scraper_status = {
    "running":     False,
    "last_run":    None,
    "last_result": "Never run",
    "error":       None,
}

# ── APP ───────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "betvibe-secret-2025")
CORS(app, resources={r"/*": {"origins": "*"}})

if HAS_SOCKETIO:
    socketio = SocketIO(
        app,
        cors_allowed_origins="*",
        async_mode="eventlet",
        logger=False,
        engineio_logger=False,
    )


# ── AUTH ──────────────────────────────────────────────────────────────
def require_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get("X-Admin-Key") or request.args.get("key")
        if key != ADMIN_KEY:
            return jsonify({"ok": False, "msg": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


# ── HELPERS ───────────────────────────────────────────────────────────
def load_matches() -> list:
    """Load matches.json. Returns [] on any error."""
    path = os.path.join(BASE_DIR, "matches.json")
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def now_ist() -> datetime:
    return datetime.now(IST)


def classify_match(row: dict) -> str:
    """Re-classify a match row at request time (more accurate than scraped status)."""
    date_ist = (row.get("date_ist") or "").strip()
    time_ist = (row.get("time_ist") or "").strip()
    toss     = (row.get("toss") or "").strip().lower()

    if not date_ist or not time_ist:
        return row.get("status", "upcoming")

    try:
        match_dt = datetime.strptime(
            f"{date_ist} {time_ist}", "%d-%m-%Y %I:%M %p"
        ).replace(tzinfo=IST)
    except ValueError:
        return row.get("status", "upcoming")

    now   = now_ist()
    end   = match_dt + timedelta(hours=10)

    # Toss announced + match ended → completed
    if toss and toss not in ("toss not announced", ""):
        if now > end:
            return "completed"
        if match_dt <= now <= end:
            return "live"
        # Rare case: toss announced before match – upcoming still
        return "upcoming"

    if now > end:
        return "completed"
    if match_dt <= now <= end:
        return "live"
    return "upcoming"


def matches_with_status() -> list:
    """Return all matches with live-computed status."""
    rows = load_matches()
    for r in rows:
        r["status"] = classify_match(r)
    return rows


def broadcast_matches():
    """Push updated match list to all connected Socket.IO clients."""
    if not HAS_SOCKETIO:
        return
    rows   = matches_with_status()
    counts = {
        "live":      sum(1 for r in rows if r["status"] == "live"),
        "upcoming":  sum(1 for r in rows if r["status"] == "upcoming"),
        "completed": sum(1 for r in rows if r["status"] == "completed"),
        "total":     len(rows),
    }
    socketio.emit("matches_update", {"matches": rows, "counts": counts})


# ── ROUTES ────────────────────────────────────────────────────────────
@app.route("/")
def home():
    return jsonify({
        "status": "BetVibe backend running ✓",
        "time_ist": now_ist().strftime("%d %b %Y %I:%M %p IST"),
        "realtime": HAS_SOCKETIO,
        "endpoints": [
            "GET  /matches.json",
            "GET  /api/matches?status=live|upcoming|completed",
            "GET  /api/health",
            "POST /api/run-scraper          (X-Admin-Key required)",
            "GET  /api/scraper-status       (X-Admin-Key required)",
            "POST /api/can-place-bet",
        ],
    })


@app.route("/api/health")
def health():
    rows   = matches_with_status()
    counts = {
        "live":      sum(1 for r in rows if r["status"] == "live"),
        "upcoming":  sum(1 for r in rows if r["status"] == "upcoming"),
        "completed": sum(1 for r in rows if r["status"] == "completed"),
        "total":     len(rows),
    }
    return jsonify({
        "ok":      True,
        "time":    now_ist().strftime("%d %b %Y %I:%M %p IST"),
        "counts":  counts,
        "scraper": scraper_status,
    })


@app.route("/matches.json")
def matches_json():
    rows = matches_with_status()
    return jsonify(rows)


@app.route("/api/matches")
def api_matches():
    """Optional ?status=live|upcoming|completed filter."""
    status_filter = request.args.get("status", "").strip().lower()
    rows = matches_with_status()

    # Sort: live first, then upcoming chronologically, then completed
    STATUS_ORDER = {"live": 0, "upcoming": 1, "completed": 2}
    rows.sort(key=lambda r: (
        STATUS_ORDER.get(r["status"], 1),
        _dt_sort(r),
    ))

    if status_filter in ("live", "upcoming", "completed"):
        rows = [r for r in rows if r["status"] == status_filter]

    counts = {
        "live":      sum(1 for r in matches_with_status() if r["status"] == "live"),
        "upcoming":  sum(1 for r in matches_with_status() if r["status"] == "upcoming"),
        "completed": sum(1 for r in matches_with_status() if r["status"] == "completed"),
    }

    return jsonify({"ok": True, "matches": rows, "counts": counts})


def _dt_sort(row: dict):
    try:
        return datetime.strptime(
            f"{row['date_ist']} {row['time_ist']}", "%d-%m-%Y %I:%M %p"
        )
    except Exception:
        return datetime.max


@app.route("/api/run-scraper", methods=["POST"])
@require_key
def trigger_scraper():
    if scraper_status["running"]:
        return jsonify({"ok": False, "msg": "Scraper already running"}), 409
    threading.Thread(target=run_scraper_task, daemon=True).start()
    return jsonify({"ok": True, "msg": "Scraper started"})


@app.route("/api/scraper-status")
@require_key
def scraper_status_api():
    return jsonify(scraper_status)


@app.route("/api/can-place-bet", methods=["POST"])
def can_place_bet():
    """
    Input  JSON: { "match": "GT vs MI" }
    Returns whether toss betting is still open (market closes 60 min before match).
    """
    body       = request.get_json(silent=True) or {}
    match_name = (body.get("match") or "").strip()

    if not match_name:
        return jsonify({"ok": False, "msg": "match field required"}), 400

    try:
        all_matches = load_matches()
    except Exception as e:
        return jsonify({"ok": False, "msg": f"Could not load matches: {e}"}), 500

    row = next(
        (m for m in all_matches
         if m.get("match") == match_name or m.get("match_link_text") == match_name),
        None,
    )

    if row is None:
        return jsonify({"ok": False, "msg": "Match not found"}), 404

    date_str = (row.get("date_ist") or "").strip()
    time_str = (row.get("time_ist") or "").strip()

    if not date_str or not time_str:
        return jsonify({"ok": False, "msg": "Match time unavailable"}), 400

    try:
        match_naive = datetime.strptime(f"{date_str} {time_str}", "%d-%m-%Y %I:%M %p")
        match_time  = match_naive.replace(tzinfo=IST)
    except ValueError:
        return jsonify({"ok": False, "msg": "Invalid match time format"}), 400

    # Use toss_close_time from JSON if present; fallback to 60 min before match
    toss_close_raw = row.get("toss_close_time")
    close_time = match_time - timedelta(minutes=60)
    if toss_close_raw:
        try:
            if isinstance(toss_close_raw, (int, float)):
                # epoch ms
                close_time = datetime.fromtimestamp(toss_close_raw / 1000, tz=IST)
            elif isinstance(toss_close_raw, str):
                # Try DD-MM-YYYY HH:MM or ISO formats
                for fmt in ("%d-%m-%Y %H:%M", "%d-%m-%Y %I:%M %p", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"):
                    try:
                        close_time = datetime.strptime(toss_close_raw, fmt).replace(tzinfo=IST)
                        break
                    except ValueError:
                        continue
        except Exception:
            pass  # fallback already set
    now        = now_ist()

    close_time_str = close_time.strftime("%d %b %Y %I:%M %p IST")
    match_time_str = match_time.strftime("%d %b %Y %I:%M %p IST")

    status = classify_match(row)

    if status == "completed":
        return jsonify({
            "ok":         False,
            "msg":        "Match already completed",
            "match_time": match_time_str,
        })

    if now >= close_time:
        return jsonify({
            "ok":         False,
            "msg":        "Toss market closed",
            "close_time": close_time_str,
            "match_time": match_time_str,
        })

    mins_left = int((close_time - now).total_seconds() / 60)
    return jsonify({
        "ok":         True,
        "msg":        "Bet allowed",
        "mins_left":  mins_left,
        "close_time": close_time_str,
        "match_time": match_time_str,
        "status":     status,
    })


# ── SOCKET.IO EVENTS ─────────────────────────────────────────────────
if HAS_SOCKETIO:
    @socketio.on("connect")
    def on_connect():
        rows   = matches_with_status()
        counts = {
            "live":      sum(1 for r in rows if r["status"] == "live"),
            "upcoming":  sum(1 for r in rows if r["status"] == "upcoming"),
            "completed": sum(1 for r in rows if r["status"] == "completed"),
            "total":     len(rows),
        }
        emit("matches_update", {"matches": rows, "counts": counts})

    @socketio.on("request_matches")
    def on_request_matches():
        rows   = matches_with_status()
        counts = {
            "live":      sum(1 for r in rows if r["status"] == "live"),
            "upcoming":  sum(1 for r in rows if r["status"] == "upcoming"),
            "completed": sum(1 for r in rows if r["status"] == "completed"),
            "total":     len(rows),
        }
        emit("matches_update", {"matches": rows, "counts": counts})


# ── SCRAPER TASK ──────────────────────────────────────────────────────
def run_scraper_task():
    scraper_status["running"] = True
    scraper_status["error"]   = None

    try:
        result = subprocess.run(
            ["python3", os.path.join(BASE_DIR, "Match_details.py")],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=BASE_DIR,
        )
        scraper_status["last_result"] = (result.stdout or "Done")[-800:]
        if result.returncode != 0:
            scraper_status["error"] = (result.stderr or "Unknown error")[-500:]
    except subprocess.TimeoutExpired:
        scraper_status["error"] = "Timed out after 5 minutes."
    except Exception as e:
        scraper_status["error"]       = str(e)
        scraper_status["last_result"] = "Failed"
    finally:
        scraper_status["running"]  = False
        scraper_status["last_run"] = now_ist().strftime("%d %b %Y %I:%M %p IST")
        # Broadcast updated data to all WS clients
        if HAS_SOCKETIO:
            try:
                broadcast_matches()
                socketio.emit("scraper_done", {
                    "status": scraper_status["last_result"],
                    "time":   scraper_status["last_run"],
                })
            except Exception:
                pass


# ── AUTO UPDATER ──────────────────────────────────────────────────────
def auto_updater():
    time.sleep(20)   # wait for app to warm up
    while True:
        if not scraper_status["running"]:
            run_scraper_task()
        # Also broadcast match status changes (live/upcoming reclassification)
        if HAS_SOCKETIO:
            try:
                broadcast_matches()
            except Exception:
                pass
        time.sleep(AUTO_REFRESH_INTERVAL)


threading.Thread(target=auto_updater, daemon=True).start()


# ── ENTRY POINT ───────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"BetVibe running on port {PORT} | SocketIO: {HAS_SOCKETIO}")
    if HAS_SOCKETIO:
        socketio.run(app, host="0.0.0.0", port=PORT, debug=False)
    else:
        app.run(host="0.0.0.0", port=PORT, debug=False)
