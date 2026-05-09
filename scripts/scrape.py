#!/usr/bin/env python3
"""
Scrapes student results from the University of Kelaniya Faculty of Science website.
Smart scraping: checks 1 student per run (every 30 min). If new result detected, scrapes all.
Saves results to data/results.json. Does NOT touch index.html.
"""

import requests
from bs4 import BeautifulSoup
import re
import time
import json
import os
import sys
import logging
from datetime import datetime, timezone, timedelta

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BASE_URL = "http://www.science.kln.ac.lk:8080"

STUDENT_IDS = [
    "EC/2022/080",
    "EC/2023/001", "EC/2023/002", "EC/2023/003", "EC/2023/004", "EC/2023/005",
    "EC/2023/006", "EC/2023/007", "EC/2023/008", "EC/2023/009", "EC/2023/010",
    "EC/2023/011", "EC/2023/012", "EC/2023/013", "EC/2023/014", "EC/2023/015",
    "EC/2023/016", "EC/2023/018", "EC/2023/020",
    "EC/2023/022", "EC/2023/023", "EC/2023/024", "EC/2023/025", "EC/2023/026",
    "EC/2023/027", "EC/2023/028", "EC/2023/029", "EC/2023/030", "EC/2023/031",
    "EC/2023/032", "EC/2023/033", "EC/2023/034", "EC/2023/035", "EC/2023/036",
    "EC/2023/037", "EC/2023/038", "EC/2023/039", "EC/2023/040", "EC/2023/041",
    "EC/2023/042", "EC/2023/043", "EC/2023/044", "EC/2023/045", "EC/2023/046",
    "EC/2023/047", "EC/2023/048", "EC/2023/049", "EC/2023/051",
    "EC/2023/052", "EC/2023/053", "EC/2023/054", "EC/2023/055", "EC/2023/056",
    "EC/2023/057", "EC/2023/060", "EC/2023/061", "EC/2023/062",
    "EC/2023/063", "EC/2023/065", "EC/2023/066",
    "EC/2023/068", "EC/2023/069", "EC/2023/070", "EC/2023/071", "EC/2023/072",
    "EC/2023/077", "EC/2023/078", "EC/2023/079", "EC/2023/080", "EC/2023/081",
    "EC/2023/082", "EC/2023/083", "EC/2023/084",
]

# IDs known to be password-protected (skip in rotation to save time)
PROTECTED_IDS = {
    "EC/2022/080", "EC/2023/004", "EC/2023/006", "EC/2023/040", "EC/2023/041",
    "EC/2023/054", "EC/2023/060", "EC/2023/065", "EC/2023/066",
    "EC/2023/070", "EC/2023/071",
}


def get_hidden_fields(soup):
    fields = {}
    for inp in soup.find_all("input", {"type": "hidden"}):
        name = inp.get("name")
        value = inp.get("value", "")
        if name:
            fields[name] = value
    return fields


def login(session, student_id):
    resp = session.get(f"{BASE_URL}/sfkn.aspx", allow_redirects=True, timeout=60)
    soup = BeautifulSoup(resp.text, "html.parser")
    hidden = get_hidden_fields(soup)
    form = soup.find("form")
    action = form.get("action", "./sfkn.aspx") if form else "./sfkn.aspx"
    current_url = resp.url
    base_session_url = current_url.rsplit("/", 1)[0]
    post_url = base_session_url + "/" + action.lstrip("./")

    data = {
        "__VIEWSTATE": hidden.get("__VIEWSTATE", ""),
        "__VIEWSTATEGENERATOR": hidden.get("__VIEWSTATEGENERATOR", ""),
        "__EVENTVALIDATION": hidden.get("__EVENTVALIDATION", ""),
        "Usernametxt": student_id,
        "PasswordTxt": "",
        "LoginBT": "Sign in",
    }

    resp2 = session.post(post_url, data=data, allow_redirects=True, timeout=60)
    return resp2


def click_year1_registration(session, resp):
    soup = BeautifulSoup(resp.text, "html.parser")
    hidden = get_hidden_fields(soup)

    year1_link = None
    for a in soup.find_all("a"):
        text = a.get_text(strip=True)
        if "Year 1" in text:
            href = a.get("href", "")
            year1_link = href
            break

    if not year1_link:
        return None, "Could not find Year 1 Registration link"

    match = re.search(r"__doPostBack\('([^']+)','([^']*)'\)", year1_link)
    if not match:
        return None, "Could not parse postback"

    event_target = match.group(1)
    event_argument = match.group(2)

    form = soup.find("form")
    action = form.get("action", "./sfkn.aspx") if form else "./sfkn.aspx"
    current_url = resp.url
    base_session_url = current_url.rsplit("/", 1)[0]
    post_url = base_session_url + "/" + action.lstrip("./")

    data = {
        "__EVENTTARGET": event_target,
        "__EVENTARGUMENT": event_argument,
        "__VIEWSTATE": hidden.get("__VIEWSTATE", ""),
        "__VIEWSTATEGENERATOR": hidden.get("__VIEWSTATEGENERATOR", ""),
        "__EVENTVALIDATION": hidden.get("__EVENTVALIDATION", ""),
    }

    resp2 = session.post(post_url, data=data, allow_redirects=True, timeout=60)
    return resp2, None


def parse_results(html, student_id):
    soup = BeautifulSoup(html, "html.parser")

    result = {
        "student_id": student_id,
        "name_initial": "",
        "full_name": "",
        "academic_year": "",
        "courses": [],
        "total_credit": "",
        "non_gpa_credit": "",
        "gpa": "",
        "error": None,
    }

    aside = soup.find("div", class_="aside")
    if aside:
        table = aside.find("table")
        if table:
            rows = table.find_all("tr")
            for row in rows:
                cells = row.find_all("td")
                if len(cells) >= 2:
                    label = cells[0].get_text(strip=True)
                    value = cells[1].get_text(strip=True)
                    if "Name with Initial" in label:
                        result["name_initial"] = value
                    elif "Full Name" in label:
                        result["full_name"] = value
                    elif "University ID" in label:
                        result["student_id"] = value
                    elif "Academic Year" in label or "Acadamic Year" in label:
                        result["academic_year"] = value

    tables = soup.find_all("table")
    for table in tables:
        headers = table.find_all("th")
        header_texts = [h.get_text(strip=True) for h in headers]
        if "Course Code" in header_texts or "CourseCode" in header_texts:
            rows = table.find_all("tr")
            for row in rows[1:]:
                cells = row.find_all("td")
                if len(cells) >= 2:
                    course = {}
                    for i, h in enumerate(header_texts):
                        if i < len(cells):
                            course[h] = cells[i].get_text(strip=True)
                    if course:
                        result["courses"].append(course)
            break

    text = soup.get_text()
    for year_label in ["1 Year", "2 Year", "3 Year", "4 Year"]:
        tc_match = re.search(rf"Total Credit \({year_label}\)\s*([\d.]+)", text)
        if tc_match:
            result["total_credit"] = tc_match.group(1)
        ngpa_match = re.search(rf"Non GPA.*?Count for GPA \({year_label}\)\s*([\d.]+)", text)
        if ngpa_match:
            result["non_gpa_credit"] = ngpa_match.group(1)
        gpa_match = re.search(rf"GPA \({year_label}\)\s*([\d.]+)", text)
        if gpa_match:
            result["gpa"] = gpa_match.group(1)
        if result["gpa"]:
            break

    return result


def scrape_student(student_id, retries=4):
    for attempt in range(retries):
        try:
            session = requests.Session()
            session.headers.update({
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
            })

            resp = login(session, student_id)

            if "Sign out" not in resp.text and "Registration" not in resp.text:
                if attempt < retries - 1:
                    time.sleep(5 * (attempt + 1))
                    continue
                return {"student_id": student_id, "error": "Login failed or no results available"}

            resp2, err = click_year1_registration(session, resp)

            if err:
                if attempt < retries - 1:
                    time.sleep(5 * (attempt + 1))
                    continue
                return {"student_id": student_id, "error": err}

            result = parse_results(resp2.text, student_id)
            return result

        except Exception as e:
            if attempt < retries - 1:
                time.sleep(8 * (attempt + 1))
                continue
            return {"student_id": student_id, "error": str(e)}


def scrape_all_students():
    all_results = []
    total = len(STUDENT_IDS)

    for i, sid in enumerate(STUDENT_IDS):
        logger.info(f"[{i+1}/{total}] Scraping {sid}...")
        result = scrape_student(sid)
        all_results.append(result)

        if result.get("error"):
            logger.warning(f"  {sid}: {result['error']}")
        else:
            logger.info(f"  {sid}: {result.get('name_initial', 'N/A')}, GPA: {result.get('gpa', 'N/A')}")

        time.sleep(1)

    return all_results


def send_telegram_notification(bot_token, chat_id, message):
    """Send a message via Telegram Bot API."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
    }
    try:
        resp = requests.post(url, json=payload, timeout=30)
        if resp.status_code == 200:
            logger.info("Telegram notification sent successfully")
        else:
            logger.error(f"Telegram notification failed: {resp.status_code} {resp.text}")
    except Exception as e:
        logger.error(f"Telegram notification error: {e}")


def detect_changes(old_results, new_results):
    """Compare old and new results to detect changes."""
    old_map = {r["student_id"]: r for r in old_results}
    new_map = {r["student_id"]: r for r in new_results}

    newly_available = []
    gpa_changes = []

    for sid, new_r in new_map.items():
        old_r = old_map.get(sid)

        # Student had no results before, now has results
        if old_r and old_r.get("error") and not new_r.get("error"):
            newly_available.append(new_r)

        # Student had results before but GPA changed
        elif old_r and not old_r.get("error") and not new_r.get("error"):
            if old_r.get("gpa") != new_r.get("gpa"):
                gpa_changes.append({"old": old_r, "new": new_r})

        # New student entirely
        elif not old_r and not new_r.get("error"):
            newly_available.append(new_r)

    return newly_available, gpa_changes


def build_notification_message(newly_available, gpa_changes, timestamp):
    """Build a Telegram notification message."""
    lines = [f"<b>New Results Update - {timestamp}</b>\n"]

    if newly_available:
        lines.append(f"<b>{len(newly_available)} NEW result(s) available:</b>")
        for r in newly_available:
            name = r.get("name_initial", "Unknown")
            gpa = r.get("gpa", "N/A")
            lines.append(f"  {r['student_id']} - {name} (GPA: {gpa})")
        lines.append("")

    if gpa_changes:
        lines.append(f"<b>{len(gpa_changes)} GPA change(s):</b>")
        for c in gpa_changes:
            sid = c["new"]["student_id"]
            old_gpa = c["old"].get("gpa", "N/A")
            new_gpa = c["new"].get("gpa", "N/A")
            lines.append(f"  {sid}: {old_gpa} -> {new_gpa}")
        lines.append("")

    total_new = len(newly_available)
    total_changes = len(gpa_changes)
    lines.append(f"Total: {total_new} new, {total_changes} changed")

    return "\n".join(lines)


def load_state(state_file):
    """Load scrape state (rotation index, timestamp)."""
    if os.path.exists(state_file):
        with open(state_file) as f:
            return json.load(f)
    return {"next_index": 0, "timestamp": "", "mode": "rotation"}


def save_state(state_file, state):
    """Save scrape state."""
    os.makedirs(os.path.dirname(state_file), exist_ok=True)
    with open(state_file, "w") as f:
        json.dump(state, f, indent=2)


def get_next_scrapeable_index(current_index):
    """Get next student index, skipping protected IDs."""
    total = len(STUDENT_IDS)
    for _ in range(total):
        current_index = current_index % total
        if STUDENT_IDS[current_index] not in PROTECTED_IDS:
            return current_index
        current_index += 1
    return 0  # fallback


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_dir = os.path.dirname(script_dir)
    data_file = os.path.join(repo_dir, "data", "results.json")
    state_file = os.path.join(repo_dir, "data", "scrape_state.json")

    # Load existing results & state
    old_results = []
    if os.path.exists(data_file):
        with open(data_file) as f:
            old_results = json.load(f)
        logger.info(f"Loaded {len(old_results)} existing results")

    state = load_state(state_file)
    ist = timezone(timedelta(hours=5, minutes=30))
    timestamp = datetime.now(ist).strftime("%Y-%m-%d %H:%M IST")

    # --- Smart scraping: check 1 student, full scrape if new result ---
    idx = get_next_scrapeable_index(state.get("next_index", 0))
    probe_sid = STUDENT_IDS[idx]
    logger.info(f"Probe scraping [{idx}] {probe_sid}...")
    probe_result = scrape_student(probe_sid)

    # Check if this student's result changed
    old_map = {r["student_id"]: r for r in old_results}
    old_probe = old_map.get(probe_sid, {})
    probe_changed = False

    if old_probe.get("error") and not probe_result.get("error"):
        probe_changed = True
        logger.info(f"NEW result detected for {probe_sid}!")
    elif not old_probe.get("error") and not probe_result.get("error"):
        if old_probe.get("gpa") != probe_result.get("gpa"):
            probe_changed = True
            logger.info(f"GPA changed for {probe_sid}!")

    if probe_changed:
        # Full scrape triggered
        logger.info("Change detected — running FULL scrape of all students...")
        new_results = scrape_all_students()
    else:
        # Just update the one student in the existing results
        logger.info(f"No change for {probe_sid}. Updating single result.")
        new_results = list(old_results)  # copy
        # Replace or add the probe result
        found = False
        for i, r in enumerate(new_results):
            if r["student_id"] == probe_sid:
                new_results[i] = probe_result
                found = True
                break
        if not found:
            new_results.append(probe_result)

    # Sort by student ID
    new_results.sort(key=lambda x: x.get("student_id", ""))

    # Detect changes for notification
    newly_available, gpa_changes = detect_changes(old_results, new_results)
    has_changes = len(newly_available) > 0 or len(gpa_changes) > 0

    if has_changes:
        logger.info(f"Changes detected: {len(newly_available)} new, {len(gpa_changes)} changed")

        # Send Telegram notification
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

        if bot_token and chat_id:
            msg = build_notification_message(newly_available, gpa_changes, timestamp)
            send_telegram_notification(bot_token, chat_id, msg)
        else:
            logger.warning("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set, skipping notification")
    else:
        logger.info("No changes detected")

    # Save results
    os.makedirs(os.path.dirname(data_file), exist_ok=True)
    with open(data_file, "w") as f:
        json.dump(new_results, f, indent=2)
    logger.info(f"Saved results to {data_file}")

    # Update state — advance to next student for next run
    next_idx = get_next_scrapeable_index(idx + 1)
    state["next_index"] = next_idx
    state["timestamp"] = timestamp
    save_state(state_file, state)
    logger.info(f"Next probe: [{next_idx}] {STUDENT_IDS[next_idx]}")

    # Set output for GitHub Actions
    github_output = os.environ.get("GITHUB_OUTPUT", "")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"has_changes={'true' if has_changes else 'false'}\n")

    success = len([r for r in new_results if not r.get("error")])
    failed = len([r for r in new_results if r.get("error")])
    logger.info(f"Final: {success} with results, {failed} errors/protected")

    return has_changes


if __name__ == "__main__":
    try:
        changed = main()
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
