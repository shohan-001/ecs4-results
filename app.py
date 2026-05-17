#!/usr/bin/env python3
"""
Flask backend for UoK Multi-Department Results Portal.
Serves static files, per-course JSON, and admin API.
"""

import json
import os
import subprocess
import threading
import time
import hashlib
import secrets
from flask import Flask, send_from_directory, jsonify, request, abort, send_file
from datetime import datetime, timezone, timedelta
from functools import wraps

app = Flask(__name__, static_folder="static")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
PROTECTED_FILE = os.path.join(BASE_DIR, "protected_creds.json")
STATUS_FILE = os.path.join(DATA_DIR, "scrape_status.json")
STATE_FILE = os.path.join(DATA_DIR, "scrape_state.json")
SCRAPER = os.path.join(BASE_DIR, "scripts", "scrape.py")

IST = timezone(timedelta(hours=5, minutes=30))

# In-memory admin sessions {token: expiry_timestamp}
admin_sessions = {}
scrape_running = False

# ---------- Helpers ----------

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {"user_password": "ecs4", "admin_password": "ecs4", "scrape_interval_minutes": 30}

def save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)

def load_json(path, default=None):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default if default is not None else {}

def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def require_admin(f):
    """Decorator: checks admin session token in Authorization header."""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        now = time.time()
        if token not in admin_sessions or admin_sessions[token] < now:
            admin_sessions.pop(token, None)
            return jsonify({"error": "Unauthorized"}), 401
        admin_sessions[token] = now + 3600  # extend session
        return f(*args, **kwargs)
    return decorated

def run_scraper_bg(args_extra=""):
    """Run scraper in background thread."""
    global scrape_running
    if scrape_running:
        return False
    scrape_running = True

    def _run():
        global scrape_running
        try:
            cmd = ["python3", SCRAPER] + (args_extra.split() if args_extra else [])
            subprocess.run(cmd, cwd=BASE_DIR, timeout=1800)
        except Exception as e:
            save_json(STATUS_FILE, {"message": f"Scraper error: {e}", "timestamp": datetime.now(IST).isoformat()})
        finally:
            scrape_running = False

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return True

def update_timer(interval_minutes):
    """Update systemd timer interval."""
    timer_file = "/etc/systemd/system/results-scraper.timer"
    if not os.path.exists(timer_file):
        return False
    try:
        with open(timer_file, "r") as f:
            content = f.read()
        import re
        content = re.sub(r"OnUnitActiveSec=\S+", f"OnUnitActiveSec={interval_minutes}min", content)
        with open(timer_file, "w") as f:
            f.write(content)
        subprocess.run(["systemctl", "daemon-reload"], timeout=10)
        subprocess.run(["systemctl", "restart", "results-scraper.timer"], timeout=10)
        return True
    except Exception as e:
        app.logger.error(f"Timer update failed: {e}")
        return False

# ---------- Static & Data Routes ----------

@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory("static", filename)

@app.route("/<path:filename>")
def root_files(filename):
    """Serve sw.js, manifest.json, icons from static/"""
    try:
        return send_from_directory("static", filename)
    except Exception:
        abort(404)

@app.route("/data/<dept>/results.json")
def dept_results(dept):
    path = os.path.join(DATA_DIR, dept, "results.json")
    if not os.path.exists(path):
        return jsonify([])
    return send_file(path, mimetype="application/json")

@app.route("/data/scrape_state.json")
def scrape_state():
    path = STATE_FILE
    if not os.path.exists(path):
        return jsonify({})
    return send_file(path, mimetype="application/json")

@app.route("/data/scrape_status.json")
def scrape_status_file():
    if not os.path.exists(STATUS_FILE):
        return jsonify({"message": "No status yet"})
    return send_file(STATUS_FILE, mimetype="application/json")

# ---------- Auth Routes ----------

@app.route("/api/login", methods=["POST"])
def user_login():
    """Verify user credentials (ecs4/ecs4)."""
    data = request.get_json() or {}
    cfg = load_config()
    if data.get("username") == "ecs4" and data.get("password") == cfg.get("user_password", "ecs4"):
        return jsonify({"ok": True})
    return jsonify({"error": "Invalid credentials"}), 401

@app.route("/api/admin/login", methods=["POST"])
def admin_login():
    """Admin login. Returns a session token."""
    data = request.get_json() or {}
    cfg = load_config()
    if data.get("username") == "admin" and data.get("password") == cfg.get("admin_password", "ecs4"):
        token = secrets.token_hex(32)
        admin_sessions[token] = time.time() + 3600
        return jsonify({"ok": True, "token": token})
    return jsonify({"error": "Invalid admin credentials"}), 401

# ---------- Admin API ----------

@app.route("/api/admin/status")
@require_admin
def admin_status():
    cfg = load_config()
    status = load_json(STATUS_FILE, {"message": "Idle"})
    state = load_json(STATE_FILE, {})
    return jsonify({
        "scrape_running": scrape_running,
        "interval_minutes": cfg.get("scrape_interval_minutes", 30),
        "last_run": state.get("last_rotation", "Never"),
        "status": status,
    })

@app.route("/api/admin/scrape", methods=["POST"])
@require_admin
def admin_scrape():
    """Trigger manual scrape."""
    data = request.get_json() or {}
    dept = data.get("dept", "")  # empty = rotation, dept code = full scrape of that dept
    mode = data.get("mode", "rotation")  # rotation | full | discover

    if scrape_running:
        return jsonify({"error": "Scraper already running"}), 409

    if mode == "discover" and dept:
        ok = run_scraper_bg(f"--discover {dept}")
    elif mode == "discover":
        ok = run_scraper_bg("--discover all")
    elif mode == "full" and dept:
        ok = run_scraper_bg(f"--full {dept}")
    elif mode == "full":
        ok = run_scraper_bg("--full all")
    else:
        ok = run_scraper_bg()

    return jsonify({"ok": ok, "message": "Scrape started" if ok else "Already running"})

@app.route("/api/admin/config", methods=["GET"])
@require_admin
def get_config():
    cfg = load_config()
    # Don't expose passwords
    return jsonify({
        "interval_minutes": cfg.get("scrape_interval_minutes", 30),
        "has_telegram": bool(cfg.get("telegram_bot_token")),
    })

@app.route("/api/admin/config", methods=["POST"])
@require_admin
def update_config():
    data = request.get_json() or {}
    cfg = load_config()

    if "interval_minutes" in data:
        interval = int(data["interval_minutes"])
        cfg["scrape_interval_minutes"] = interval
        update_timer(interval)

    if "user_password" in data and data["user_password"]:
        cfg["user_password"] = data["user_password"]

    if "admin_password" in data and data["admin_password"]:
        cfg["admin_password"] = data["admin_password"]

    if "telegram_bot_token" in data:
        cfg["telegram_bot_token"] = data["telegram_bot_token"]
    if "telegram_chat_id" in data:
        cfg["telegram_chat_id"] = data["telegram_chat_id"]

    save_config(cfg)
    return jsonify({"ok": True})

@app.route("/api/admin/protected", methods=["GET"])
@require_admin
def list_protected():
    """List all protected students (IDs only, no passwords)."""
    creds = load_json(PROTECTED_FILE, {})
    # Find protected students from all dept results
    protected_ids = []
    import glob
    for path in glob.glob(os.path.join(DATA_DIR, "*/results.json")):
        dept = os.path.basename(os.path.dirname(path))
        data = load_json(path, [])
        for r in data:
            if r.get("error") in ("protected", "no_year1"):
                protected_ids.append({
                    "student_id": r["student_id"],
                    "dept": dept,
                    "has_password": r["student_id"] in creds,
                    "error": r.get("error"),
                })
    return jsonify(protected_ids)

@app.route("/api/admin/protected", methods=["POST"])
@require_admin
def set_protected():
    """Save a protected student's password."""
    data = request.get_json() or {}
    sid = data.get("student_id", "").strip()
    pwd = data.get("password", "").strip()
    if not sid:
        return jsonify({"error": "student_id required"}), 400

    creds = load_json(PROTECTED_FILE, {})
    if pwd:
        creds[sid] = pwd
    else:
        creds.pop(sid, None)  # Remove if blank

    save_json(PROTECTED_FILE, creds)
    return jsonify({"ok": True})

@app.route("/api/admin/protected/<sid>", methods=["DELETE"])
@require_admin
def delete_protected(sid):
    creds = load_json(PROTECTED_FILE, {})
    creds.pop(sid, None)
    save_json(PROTECTED_FILE, creds)
    return jsonify({"ok": True})

if __name__ == "__main__":
    os.makedirs(DATA_DIR, exist_ok=True)
    # Init config if missing
    if not os.path.exists(CONFIG_FILE):
        save_config({
            "user_password": "ecs4",
            "admin_password": "ecs4",
            "scrape_interval_minutes": 30,
            "telegram_bot_token": "",
            "telegram_chat_id": "",
            "base_url": "http://www.science.kln.ac.lk:8080",
        })
    app.run(host="127.0.0.1", port=5000, debug=False)
