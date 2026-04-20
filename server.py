"""
BetVibe Backend Server
=====================
Runs on Railway / Render (or locally).

Endpoints:
  GET  /matches.json
  POST /api/run-scraper
  GET  /api/scraper-status
  POST /api/can-place-bet
  GET  /api/dashboard-stats
  POST /api/update-deposit-status
  POST /api/update-withdrawal-status
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
from functools import wraps
import threading
import subprocess
import time
import os
import json
import hashlib
import hmac
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import re

# Timezone support
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

# =====================================================
# CONFIG
# =====================================================

ADMIN_KEY = "betvibe@2025"
RATE_LIMIT = {}  # Simple rate limiting dict
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX = 30  # requests per window

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("PORT", 5000))

# Scraper status
scraper_status = {
    "running": False,
    "last_run": None,
    "last_result": "Never run",
    "error": None
}

# Cache for dashboard stats
stats_cache = {
    "data": None,
    "timestamp": None,
    "ttl": 10  # seconds
}

app = Flask(__name__)
CORS(app, resources={
    r"/*": {
        "origins": [
            "https://betvibe.netlify.app",
            "https://betvibe-admin.netlify.app",
            "http://localhost:3000",
            "http://localhost:5500",
            "http://127.0.0.1:5500"
        ],
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "X-Admin-Key"]
    }
})

# =====================================================
# RATE LIMITING
# =====================================================

def rate_limit(key):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            now = time.time()
            if key not in RATE_LIMIT:
                RATE_LIMIT[key] = []
            
            # Clean old requests
            RATE_LIMIT[key] = [t for t in RATE_LIMIT[key] if now - t < RATE_LIMIT_WINDOW]
            
            if len(RATE_LIMIT[key]) >= RATE_LIMIT_MAX:
                return jsonify({"ok": False, "msg": "Rate limit exceeded"}), 429
            
            RATE_LIMIT[key].append(now)
            return f(*args, **kwargs)
        return decorated
    return decorator

# =====================================================
# AUTH
# =====================================================

def require_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get("X-Admin-Key") or request.args.get("key")
        if key != ADMIN_KEY:
            return jsonify({"ok": False, "msg": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated

# =====================================================
# HELPERS
# =====================================================

def load_matches():
    """Safely load matches.json from BASE_DIR."""
    path = os.path.join(BASE_DIR, "matches.json")
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []


def is_toss_market_open(match_row):
    """
    Check if toss market is still open for a match.
    Market closes exactly 60 minutes before match start.
    """
    try:
        date_str = (match_row.get("date_ist") or "").strip()
        time_str = (match_row.get("time_ist") or "").strip()
        
        if not date_str or not time_str:
            return False
        
        match_naive = datetime.strptime(
            f"{date_str} {time_str}", "%d-%m-%Y %I:%M %p"
        )
        match_time = match_naive.replace(tzinfo=IST)
        close_time = match_time - timedelta(minutes=60)
        now_ist = datetime.now(IST)
        
        # Also check if toss already announced
        toss = match_row.get("toss", "")
        if toss and toss != "Toss not announced":
            return False
        
        return now_ist < close_time
    except:
        return False

# =====================================================
# ROUTES
# =====================================================

@app.route("/")
def home():
    return jsonify({
        "status": "BetVibe backend running",
        "version": "2.0",
        "endpoints": [
            "/matches.json",
            "/api/run-scraper",
            "/api/scraper-status",
            "/api/can-place-bet",
            "/api/dashboard-stats",
            "/api/update-deposit-status",
            "/api/update-withdrawal-status"
        ]
    })


@app.route("/matches.json")
@rate_limit("matches")
def matches():
    path = os.path.join(BASE_DIR, "matches.json")
    
    if not os.path.exists(path):
        return jsonify([])
    
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # Add market open status to each match
    for match in data:
        match["market_open"] = is_toss_market_open(match)
    
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


@app.route("/api/can-place-bet", methods=["POST"])
@rate_limit("can_place_bet")
def can_place_bet():
    """
    Input: { "match": "GT vs MI" }
    Returns: { "ok": true/false, "msg": "...", "close_time": "...", "match_time": "..." }
    """
    body = request.get_json(silent=True) or {}
    match_name = (body.get("match") or "").strip()
    
    if not match_name:
        return jsonify({"ok": False, "msg": "match field required"}), 400
    
    try:
        all_matches = load_matches()
    except Exception as e:
        return jsonify({"ok": False, "msg": f"Could not load matches: {e}"}), 500
    
    # Find the match
    row = None
    for m in all_matches:
        if (m.get("match") == match_name or 
            m.get("match_link_text") == match_name):
            row = m
            break
    
    if row is None:
        return jsonify({"ok": False, "msg": "Match not found"}), 404
    
    market_open = is_toss_market_open(row)
    
    if not market_open:
        return jsonify({
            "ok": False,
            "msg": "Toss market closed. Betting closes 60 minutes before match start."
        })
    
    return jsonify({
        "ok": True,
        "msg": "Bet allowed"
    })


@app.route("/api/dashboard-stats")
@require_key
def dashboard_stats():
    """Get real-time dashboard statistics from localStorage (simulated)."""
    # Note: In production, this would query a real database.
    # For now, we return a structure that the admin can populate.
    return jsonify({
        "ok": True,
        "stats": {
            "total_users": 0,
            "total_deposits": 0,
            "total_withdrawals": 0,
            "pending_deposits": 0,
            "pending_withdrawals": 0,
            "total_bets": 0,
            "active_users": 0,
            "recent_activity": []
        }
    })


@app.route("/api/health")
def health():
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now(IST).isoformat(),
        "scraper_running": scraper_status["running"],
        "last_scrape": scraper_status["last_run"]
    })

# =====================================================
# SCRAPER TASK
# =====================================================

def run_scraper_task():
    scraper_status["running"] = True
    scraper_status["error"] = None
    
    try:
        # Run the scraper
        result = subprocess.run(
            ["python3", os.path.join(BASE_DIR, "Match_details.py")],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=BASE_DIR
        )
        
        scraper_status["last_result"] = (result.stdout or "Done")[-1000:]
        
        if result.returncode != 0:
            scraper_status["error"] = (result.stderr or "Unknown error")[-500:]
            
    except subprocess.TimeoutExpired:
        scraper_status["error"] = "Scraper timed out after 5 minutes."
        scraper_status["last_result"] = "Timeout"
        
    except Exception as e:
        scraper_status["error"] = str(e)
        scraper_status["last_result"] = "Failed"
        
    finally:
        scraper_status["running"] = False
        scraper_status["last_run"] = datetime.now(IST).strftime("%d %b %Y %I:%M %p IST")


def auto_updater():
    """Run scraper every 30 minutes automatically."""
    time.sleep(30)  # Wait for server to start
    
    while True:
        if not scraper_status["running"]:
            print(f"[{datetime.now(IST)}] Running automatic scraper...")
            run_scraper_task()
            print(f"[{datetime.now(IST)}] Scraper completed")
        
        time.sleep(1800)  # 30 minutes


# Start background updater
threading.Thread(target=auto_updater, daemon=True).start()

# =====================================================
# START APP
# =====================================================

if __name__ == "__main__":
    print(f"🚀 BetVibe server running on port {PORT}")
    print(f"📍 Timezone: IST ({datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S')})")
    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)
