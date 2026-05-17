#!/usr/bin/env python3
"""
Multi-department async scraper for UoK Faculty of Science Results Portal.
Departments: EC, PS, PE, SS, BS, AC, EM, SE

Modes:
  python scrape.py                  # Smart rotation (1 per dept)
  python scrape.py --discover ec    # Discover all students in a dept
  python scrape.py --discover all   # Discover all students in all depts
  python scrape.py --full ec        # Full scrape existing students in dept
  python scrape.py --full all       # Full scrape all depts
"""

import requests
from bs4 import BeautifulSoup
import re
import time
import json
import os
import sys
import logging
import argparse
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))
CONCURRENCY = 5          # max concurrent requests per batch
DISCOVER_CONCURRENCY = 8 # concurrent during discovery
MAX_CONSEC_FAILURES = 20 # stop discovery after N consecutive login failures

# --- Config ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(SCRIPT_DIR)
CONFIG_FILE = os.path.join(REPO_DIR, "config.json")
PROTECTED_FILE = os.path.join(REPO_DIR, "protected_creds.json")
DATA_DIR = os.path.join(REPO_DIR, "data")
STATE_FILE = os.path.join(DATA_DIR, "scrape_state.json")
STATUS_FILE = os.path.join(DATA_DIR, "scrape_status.json")

DEPARTMENTS = {
    "ec": {"name": "Electronics & Computer Science", "prefix": "EC", "year": "2023", "max_n": 90,  "extra": ["EC/2022/080"]},
    "ps": {"name": "Physical Science",               "prefix": "PS", "year": "2023", "max_n": 500, "extra": []},
    "pe": {"name": "Physics & Electronics",          "prefix": "PE", "year": "2023", "max_n": 100, "extra": []},
    "ss": {"name": "Sport Science",                  "prefix": "SS", "year": "2023", "max_n": 70,  "extra": []},
    "bs": {"name": "Biological Science",             "prefix": "BS", "year": "2023", "max_n": 300, "extra": []},
    "ac": {"name": "Applied Chemistry",              "prefix": "AC", "year": "2023", "max_n": 80,  "extra": []},
    "em": {"name": "Environmental Management",       "prefix": "EM", "year": "2023", "max_n": 150, "extra": []},
    "se": {"name": "Software Engineering",           "prefix": "SE", "year": "2023", "max_n": 80,  "extra": []},
}

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {"base_url": "http://www.science.kln.ac.lk:8080", "telegram_bot_token": "", "telegram_chat_id": ""}

def load_protected_creds():
    if os.path.exists(PROTECTED_FILE):
        with open(PROTECTED_FILE) as f:
            return json.load(f)
    return {}

def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def load_json(path, default=None):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default if default is not None else []

def dept_results_file(dept_code):
    return os.path.join(DATA_DIR, dept_code, "results.json")

def update_status(msg, progress=None, dept=None):
    status = {"message": msg, "timestamp": datetime.now(IST).isoformat()}
    if progress is not None:
        status["progress"] = progress
    if dept:
        status["department"] = dept
    save_json(STATUS_FILE, status)
    logger.info(msg)

# ---------- University Portal Scraping ----------

def get_hidden_fields(soup):
    fields = {}
    for inp in soup.find_all("input", {"type": "hidden"}):
        name = inp.get("name")
        value = inp.get("value", "")
        if name:
            fields[name] = value
    return fields

def portal_login(session, student_id, password, base_url):
    resp = session.get(f"{base_url}/sfkn.aspx", allow_redirects=True, timeout=60)
    soup = BeautifulSoup(resp.text, "html.parser")
    hidden = get_hidden_fields(soup)
    form = soup.find("form")
    action = form.get("action", "./sfkn.aspx") if form else "./sfkn.aspx"
    base_session_url = resp.url.rsplit("/", 1)[0]
    post_url = base_session_url + "/" + action.lstrip("./")

    data = {
        "__VIEWSTATE": hidden.get("__VIEWSTATE", ""),
        "__VIEWSTATEGENERATOR": hidden.get("__VIEWSTATEGENERATOR", ""),
        "__EVENTVALIDATION": hidden.get("__EVENTVALIDATION", ""),
        "Usernametxt": student_id,
        "PasswordTxt": password,
        "LoginBT": "Sign in",
    }
    resp2 = session.post(post_url, data=data, allow_redirects=True, timeout=60)
    return resp2

def is_login_success(resp_text):
    return "Sign out" in resp_text or "Registration" in resp_text

def is_protected(resp_text):
    """Detect password-protected account (login fails with blank pwd)."""
    lowered = resp_text.lower()
    return ("password" in lowered and "incorrect" in lowered) or \
           ("invalid" in lowered and "password" in lowered) or \
           ("please enter" in lowered and "password" in lowered)

def is_no_account(resp_text):
    """Detect completely non-existent student ID."""
    lowered = resp_text.lower()
    return ("invalid" in lowered and "username" in lowered) or \
           ("user not found" in lowered) or \
           ("no user" in lowered)

def click_year1(session, resp, base_url):
    soup = BeautifulSoup(resp.text, "html.parser")
    hidden = get_hidden_fields(soup)
    year1_link = None
    for a in soup.find_all("a"):
        if "Year 1" in a.get_text():
            year1_link = a.get("href", "")
            break
    if not year1_link:
        return None, "no_year1"

    match = re.search(r"__doPostBack\('([^']+)','([^']*)'\)", year1_link)
    if not match:
        return None, "no_year1"

    form = soup.find("form")
    action = form.get("action", "./sfkn.aspx") if form else "./sfkn.aspx"
    base_session_url = resp.url.rsplit("/", 1)[0]
    post_url = base_session_url + "/" + action.lstrip("./")

    data = {
        "__EVENTTARGET": match.group(1),
        "__EVENTARGUMENT": match.group(2),
        "__VIEWSTATE": hidden.get("__VIEWSTATE", ""),
        "__VIEWSTATEGENERATOR": hidden.get("__VIEWSTATEGENERATOR", ""),
        "__EVENTVALIDATION": hidden.get("__EVENTVALIDATION", ""),
    }
    resp2 = session.post(post_url, data=data, allow_redirects=True, timeout=60)
    return resp2, None

def parse_results(html, student_id):
    soup = BeautifulSoup(html, "html.parser")
    result = {
        "student_id": student_id, "name_initial": "", "full_name": "",
        "academic_year": "", "courses": [], "total_credit": "",
        "non_gpa_credit": "", "gpa": "", "error": None,
    }
    aside = soup.find("div", class_="aside")
    if aside:
        table = aside.find("table")
        if table:
            for row in table.find_all("tr"):
                cells = row.find_all("td")
                if len(cells) >= 2:
                    label = cells[0].get_text(strip=True)
                    value = cells[1].get_text(strip=True)
                    if "Name with Initial" in label: result["name_initial"] = value
                    elif "Full Name" in label: result["full_name"] = value
                    elif "Academic Year" in label or "Acadamic Year" in label: result["academic_year"] = value

    for table in soup.find_all("table"):
        headers = [h.get_text(strip=True) for h in table.find_all("th")]
        if "Course Code" in headers or "CourseCode" in headers:
            for row in table.find_all("tr")[1:]:
                cells = row.find_all("td")
                if cells:
                    course = {headers[i]: cells[i].get_text(strip=True) for i in range(min(len(headers), len(cells)))}
                    if course:
                        result["courses"].append(course)
            break

    text = soup.get_text()
    for yr in ["1 Year", "2 Year", "3 Year", "4 Year"]:
        m = re.search(rf"GPA \({yr}\)\s*([\d.]+)", text)
        if m: result["gpa"] = m.group(1)
        m = re.search(rf"Total Credit \({yr}\)\s*([\d.]+)", text)
        if m: result["total_credit"] = m.group(1)
        if result["gpa"]: break

    return result

def scrape_student(student_id, password="", base_url=None, retries=3):
    """Scrape one student. Returns result dict with 'error' key for failures."""
    if base_url is None:
        cfg = load_config()
        base_url = cfg.get("base_url", "http://www.science.kln.ac.lk:8080")

    for attempt in range(retries):
        try:
            session = requests.Session()
            session.headers.update({"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"})
            resp = portal_login(session, student_id, password, base_url)

            if not is_login_success(resp.text):
                # Detect why login failed
                if is_protected(resp.text):
                    return {"student_id": student_id, "error": "protected"}
                elif is_no_account(resp.text):
                    return {"student_id": student_id, "error": "no_account"}
                else:
                    # Ambiguous: might be protected or no account
                    # Mark as protected so admin can try a password
                    return {"student_id": student_id, "error": "protected"}

            resp2, err = click_year1(session, resp, base_url)
            if err:
                return {"student_id": student_id, "error": "no_year1"}

            result = parse_results(resp2.text, student_id)
            if not result["name_initial"] and not result["courses"]:
                return {"student_id": student_id, "error": "empty_result"}

            return result

        except Exception as e:
            if attempt < retries - 1:
                time.sleep(5 * (attempt + 1))
                continue
            return {"student_id": student_id, "error": str(e)}

# ---------- Discovery Mode ----------

def generate_ids(dept_code):
    info = DEPARTMENTS[dept_code]
    ids = list(info.get("extra", []))
    for n in range(1, info["max_n"] + 1):
        ids.append(f"{info['prefix']}/{info['year']}/{n:03d}")
    return ids

def discover_department(dept_code, base_url):
    """Probe all IDs for a department. Skips non-existent. Marks protected."""
    ids = generate_ids(dept_code)
    total = len(ids)
    results, protected = [], []
    consec_failures = 0
    done = 0

    update_status(f"Discovering {dept_code.upper()} ({total} IDs to probe)...", 0, dept_code)

    # Process in batches
    for batch_start in range(0, total, DISCOVER_CONCURRENCY):
        batch = ids[batch_start:batch_start + DISCOVER_CONCURRENCY]
        creds = load_protected_creds()

        with ThreadPoolExecutor(max_workers=DISCOVER_CONCURRENCY) as ex:
            futures = {ex.submit(scrape_student, sid, creds.get(sid, ""), base_url): sid for sid in batch}
            for future in as_completed(futures):
                sid = futures[future]
                result = future.result()
                done += 1

                if result.get("error") == "no_account":
                    consec_failures += 1
                elif result.get("error") == "protected":
                    protected.append({"student_id": sid, "error": "protected"})
                    consec_failures = 0
                elif result.get("error") == "no_year1":
                    # Student exists but no Year 1 results yet — keep in protected list
                    protected.append({"student_id": sid, "error": "no_year1"})
                    consec_failures = 0
                elif result.get("error"):
                    consec_failures += 1
                else:
                    results.append(result)
                    consec_failures = 0

        pct = int(done / total * 100)
        update_status(f"Discovering {dept_code.upper()}: {done}/{total} ({pct}%)", pct, dept_code)

        if consec_failures >= MAX_CONSEC_FAILURES:
            logger.info(f"  [{dept_code}] Stopped early after {MAX_CONSEC_FAILURES} consecutive failures at n={batch_start + DISCOVER_CONCURRENCY}")
            break

        time.sleep(1)  # Be polite between batches

    return results, protected

# ---------- Full Scrape Mode ----------

def full_scrape_department(dept_code, base_url):
    """Rescrape all known students in a department."""
    existing = load_json(dept_results_file(dept_code), [])
    creds = load_protected_creds()

    # Get IDs to scrape: existing successes + protected with passwords
    ids_to_scrape = []
    for r in existing:
        sid = r["student_id"]
        if r.get("error") == "protected" and sid in creds:
            ids_to_scrape.append((sid, creds[sid]))
        elif not r.get("error"):
            ids_to_scrape.append((sid, ""))

    if not ids_to_scrape:
        logger.info(f"  [{dept_code}] No students to scrape")
        return existing

    total = len(ids_to_scrape)
    new_results_map = {}
    done = 0
    update_status(f"Full scraping {dept_code.upper()} ({total} students)...", 0, dept_code)

    for batch_start in range(0, total, CONCURRENCY):
        batch = ids_to_scrape[batch_start:batch_start + CONCURRENCY]
        with ThreadPoolExecutor(max_workers=CONCURRENCY) as ex:
            futures = {ex.submit(scrape_student, sid, pwd, base_url): sid for sid, pwd in batch}
            for future in as_completed(futures):
                sid = futures[future]
                new_results_map[sid] = future.result()
                done += 1

        pct = int(done / total * 100)
        update_status(f"Scraping {dept_code.upper()}: {done}/{total} ({pct}%)", pct, dept_code)
        time.sleep(0.5)

    # Merge: keep protected/no_year1 from existing if still failing
    merged = []
    existing_map = {r["student_id"]: r for r in existing}
    seen = set()

    for sid, new_r in new_results_map.items():
        if new_r.get("error") in ("no_account",):
            pass  # Remove from DB
        else:
            merged.append(new_r)
        seen.add(sid)

    # Keep existing protected entries that we didn't re-scrape
    for r in existing:
        if r["student_id"] not in seen:
            merged.append(r)

    merged.sort(key=lambda x: x.get("student_id", ""))
    return merged

# ---------- Smart Rotation ----------

def rotation_probe(base_url):
    """Probe 1 student per department. Returns dict of {dept: changed}."""
    state = load_json(STATE_FILE, {})
    creds = load_protected_creds()
    changed_depts = []

    for dept_code in DEPARTMENTS:
        dept_data = load_json(dept_results_file(dept_code), [])
        # Get a non-protected student to probe
        probe_sid = None
        for r in dept_data:
            if not r.get("error"):
                probe_sid = r["student_id"]
                break

        if not probe_sid:
            logger.info(f"  [{dept_code}] No probe candidate, skipping")
            continue

        logger.info(f"  [{dept_code}] Probing {probe_sid}...")
        new_r = scrape_student(probe_sid, "", base_url)
        old_r = next((r for r in dept_data if r["student_id"] == probe_sid), {})

        # Detect change
        changed = False
        if old_r.get("error") and not new_r.get("error"):
            changed = True  # was error, now has result
        elif not old_r.get("error") and not new_r.get("error"):
            if old_r.get("gpa") != new_r.get("gpa"):
                changed = True
            if len(old_r.get("courses", [])) != len(new_r.get("courses", [])):
                changed = True

        if changed:
            logger.info(f"  [{dept_code}] CHANGE DETECTED for {probe_sid}!")
            changed_depts.append(dept_code)

    return changed_depts

# ---------- Notifications ----------

def send_telegram(token, chat_id, message):
    if not token or not chat_id:
        return
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"}, timeout=30)
        logger.info("Telegram notification sent")
    except Exception as e:
        logger.error(f"Telegram error: {e}")

def build_notification(newly_available, gpa_changes, timestamp):
    lines = [f"<b>UoK Results Update — {timestamp}</b>"]
    if newly_available:
        lines.append(f"\n<b>{len(newly_available)} new result(s):</b>")
        for r in newly_available[:10]:
            lines.append(f"  {r['student_id']} - {r.get('name_initial','?')} (GPA: {r.get('gpa','?')})")
    if gpa_changes:
        lines.append(f"\n<b>{len(gpa_changes)} GPA change(s):</b>")
        for c in gpa_changes[:5]:
            lines.append(f"  {c['id']}: {c['old']} → {c['new']}")
    return "\n".join(lines)

def detect_changes(old_list, new_list):
    old_map = {r["student_id"]: r for r in old_list}
    new_map = {r["student_id"]: r for r in new_list}
    new_results, gpa_changes = [], []

    for sid, new_r in new_map.items():
        old_r = old_map.get(sid, {})
        if (old_r.get("error") or not old_r) and not new_r.get("error"):
            new_results.append(new_r)
        elif not old_r.get("error") and not new_r.get("error"):
            if old_r.get("gpa") != new_r.get("gpa"):
                gpa_changes.append({"id": sid, "old": old_r.get("gpa"), "new": new_r.get("gpa")})

    return new_results, gpa_changes

# ---------- Main ----------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--discover", metavar="DEPT", help="Discovery mode: dept code or 'all'")
    parser.add_argument("--full", metavar="DEPT", help="Full scrape: dept code or 'all'")
    args = parser.parse_args()

    cfg = load_config()
    base_url = cfg.get("base_url", "http://www.science.kln.ac.lk:8080")
    tg_token = cfg.get("telegram_bot_token", "")
    tg_chat = cfg.get("telegram_chat_id", "")
    timestamp = datetime.now(IST).strftime("%Y-%m-%d %H:%M IST")

    update_status("Scraper started", 0)

    # --- DISCOVER MODE ---
    if args.discover:
        target_depts = list(DEPARTMENTS.keys()) if args.discover == "all" else [args.discover.lower()]
        for dept_code in target_depts:
            if dept_code not in DEPARTMENTS:
                logger.error(f"Unknown department: {dept_code}")
                continue
            logger.info(f"=== Discovering {dept_code.upper()} ===")
            results, protected = discover_department(dept_code, base_url)
            combined = results + protected
            combined.sort(key=lambda x: x.get("student_id", ""))
            save_json(dept_results_file(dept_code), combined)
            logger.info(f"  [{dept_code}] Found {len(results)} students, {len(protected)} protected")

        update_status("Discovery complete", 100)
        return

    # --- FULL SCRAPE MODE ---
    if args.full:
        target_depts = list(DEPARTMENTS.keys()) if args.full == "all" else [args.full.lower()]
        all_newly_available, all_gpa_changes = [], []
        for dept_code in target_depts:
            if dept_code not in DEPARTMENTS:
                continue
            logger.info(f"=== Full scrape {dept_code.upper()} ===")
            old_data = load_json(dept_results_file(dept_code), [])
            new_data = full_scrape_department(dept_code, base_url)
            save_json(dept_results_file(dept_code), new_data)
            newly, changes = detect_changes(old_data, new_data)
            all_newly_available.extend(newly)
            all_gpa_changes.extend(changes)
            logger.info(f"  [{dept_code}] {len(new_data)} records, {len(newly)} new, {len(changes)} changed")

        if all_newly_available or all_gpa_changes:
            msg = build_notification(all_newly_available, all_gpa_changes, timestamp)
            send_telegram(tg_token, tg_chat, msg)

        update_status("Full scrape complete", 100)
        return

    # --- ROTATION MODE (default) ---
    logger.info("=== Rotation probe mode ===")
    changed_depts = rotation_probe(base_url)

    all_newly, all_changes = [], []
    if changed_depts:
        logger.info(f"Changes detected in: {changed_depts}. Running full scrape for those departments...")
        for dept_code in changed_depts:
            old_data = load_json(dept_results_file(dept_code), [])
            new_data = full_scrape_department(dept_code, base_url)
            save_json(dept_results_file(dept_code), new_data)
            newly, changes = detect_changes(old_data, new_data)
            all_newly.extend(newly)
            all_changes.extend(changes)
    else:
        logger.info("No changes detected in any department.")

    if all_newly or all_changes:
        msg = build_notification(all_newly, all_changes, timestamp)
        send_telegram(tg_token, tg_chat, msg)

    # Update state timestamp
    state = load_json(STATE_FILE, {})
    state["last_rotation"] = timestamp
    save_json(STATE_FILE, state)

    update_status(f"Rotation complete — {len(all_newly)} new, {len(all_changes)} changed", 100)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"Fatal: {e}", exc_info=True)
        update_status(f"Error: {e}", -1)
        sys.exit(1)
