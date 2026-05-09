#!/usr/bin/env python3
"""
Scrapes student results from the University of Kelaniya Faculty of Science website.
Compares with existing results and sends Telegram notification if new results found.
Generates an updated index.html with embedded data.
"""

import requests
from bs4 import BeautifulSoup
import re
import time
import json
import os
import sys
import logging
from datetime import datetime, timezone

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

    total_new = len([r for r in newly_available])
    total_changes = len(gpa_changes)
    lines.append(f"Total: {total_new} new, {total_changes} changed")

    return "\n".join(lines)


def generate_html(results, timestamp):
    """Generate the index.html with embedded results data."""
    results.sort(key=lambda x: x.get("student_id", ""))

    data_json = json.dumps(results)

    success = [r for r in results if not r.get("error")]
    failed = [r for r in results if r.get("error")]
    gpas = [float(r["gpa"]) for r in success if r.get("gpa")]
    avg_gpa = sum(gpas) / len(gpas) if gpas else 0
    max_gpa = max(gpas) if gpas else 0
    min_gpa = min(gpas) if gpas else 0

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Faculty of Science - Student Results</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f0f2f5; color: #333; }}
.header {{ background: linear-gradient(135deg, #1a73e8, #0d47a1); color: white; padding: 24px; text-align: center; }}
.header h1 {{ font-size: 1.6em; margin-bottom: 4px; }}
.header p {{ opacity: 0.9; font-size: 0.95em; }}
.header .meta {{ font-size: 0.8em; opacity: 0.75; margin-top: 8px; }}
.container {{ max-width: 1200px; margin: 20px auto; padding: 0 16px; }}
.summary-bar {{ display: flex; gap: 12px; margin-bottom: 20px; flex-wrap: wrap; }}
.summary-card {{ background: white; border-radius: 8px; padding: 14px 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); flex: 1; min-width: 120px; text-align: center; }}
.summary-card .num {{ font-size: 1.8em; font-weight: 700; }}
.summary-card .label {{ font-size: 0.78em; color: #666; margin-top: 2px; }}
.blue {{ color: #1a73e8; }}
.green {{ color: #2e7d32; }}
.red {{ color: #c62828; }}
.search-bar {{ margin-bottom: 20px; display: flex; gap: 10px; }}
.search-bar input {{ flex: 1; padding: 12px 16px; border: 1px solid #ddd; border-radius: 8px; font-size: 1em; outline: none; }}
.search-bar input:focus {{ border-color: #1a73e8; box-shadow: 0 0 0 2px rgba(26,115,232,0.2); }}
.sort-btn {{ padding: 12px 16px; border: 1px solid #ddd; border-radius: 8px; background: white; cursor: pointer; font-size: 0.9em; white-space: nowrap; }}
.sort-btn:hover {{ background: #f0f2f5; }}
.sort-btn.active {{ background: #1a73e8; color: white; border-color: #1a73e8; }}
.student-card {{ background: white; border-radius: 8px; margin-bottom: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); overflow: hidden; }}
.student-header {{ display: flex; justify-content: space-between; align-items: center; padding: 14px 18px; cursor: pointer; user-select: none; }}
.student-header:hover {{ background: #f8f9fa; }}
.student-info {{ flex: 1; }}
.student-id {{ font-weight: 700; color: #1a73e8; font-size: 1em; }}
.student-name {{ color: #555; font-size: 0.85em; margin-top: 1px; }}
.student-gpa {{ text-align: right; }}
.gpa-value {{ font-size: 1.4em; font-weight: 700; }}
.gpa-label {{ font-size: 0.7em; color: #888; }}
.gpa-high {{ color: #2e7d32; }}
.gpa-mid {{ color: #f57f17; }}
.gpa-low {{ color: #c62828; }}
.student-details {{ display: none; padding: 0 18px 14px; border-top: 1px solid #eee; }}
.student-details.open {{ display: block; }}
.course-table {{ width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 0.85em; }}
.course-table th {{ background: #f0f2f5; padding: 7px 8px; text-align: left; font-weight: 600; border-bottom: 2px solid #ddd; }}
.course-table td {{ padding: 6px 8px; border-bottom: 1px solid #eee; }}
.course-table tr:hover td {{ background: #f8f9fa; }}
.grade-a {{ color: #2e7d32; font-weight: 600; }}
.grade-b {{ color: #1565c0; font-weight: 600; }}
.grade-c {{ color: #f57f17; font-weight: 600; }}
.grade-d {{ color: #e65100; font-weight: 600; }}
.grade-fail {{ color: #c62828; font-weight: 600; }}
.no-results {{ background: white; border-radius: 8px; padding: 14px 18px; margin-bottom: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); color: #999; }}
.no-results .student-id {{ color: #c62828; }}
.toggle-icon {{ font-size: 1.1em; color: #999; margin-left: 10px; transition: transform 0.2s; }}
.toggle-icon.open {{ transform: rotate(90deg); }}
.absent {{ color: #c62828; font-style: italic; }}
.detail-meta {{ margin-bottom: 8px; color: #666; font-size: 0.82em; }}
.count-badge {{ display: inline-block; background: #e8eaf6; color: #3f51b5; padding: 2px 8px; border-radius: 10px; font-size: 0.8em; margin-left: 4px; }}
@media (max-width: 600px) {{
  .summary-bar {{ flex-direction: column; }}
  .student-header {{ flex-direction: column; align-items: flex-start; gap: 6px; }}
  .student-gpa {{ text-align: left; }}
  .course-table {{ font-size: 0.75em; }}
  .search-bar {{ flex-direction: column; }}
}}
</style>
</head>
<body>
<div class="header">
  <h1>University of Kelaniya - Faculty of Science</h1>
  <p>First Year Exam Results (2023/2024)</p>
  <p class="meta">Last updated: {timestamp} | Auto-scraped every 6 hours</p>
</div>
<div class="container">
  <div class="summary-bar">
    <div class="summary-card"><div class="num blue">{len(results)}</div><div class="label">Total Students</div></div>
    <div class="summary-card"><div class="num green">{len(success)}</div><div class="label">Results Available</div></div>
    <div class="summary-card"><div class="num blue">{avg_gpa:.2f}</div><div class="label">Average GPA</div></div>
    <div class="summary-card"><div class="num green">{max_gpa:.2f}</div><div class="label">Highest GPA</div></div>
    <div class="summary-card"><div class="num red">{min_gpa:.2f}</div><div class="label">Lowest GPA</div></div>
  </div>

  <div class="search-bar">
    <input type="text" id="searchInput" placeholder="Search by student ID, name, or course code..." oninput="render()">
    <button class="sort-btn" id="sortBtn" onclick="toggleSort()">Sort: Default</button>
  </div>

  <div id="studentList"></div>
</div>

<script>
var DATA = {data_json};
var sortMode = 'default';
var expanded = {{}};

function gradeClass(g) {{
  if (!g) return '';
  var u = g.trim().toUpperCase();
  if (u.startsWith('A')) return 'grade-a';
  if (u.startsWith('B')) return 'grade-b';
  if (u.startsWith('C')) return 'grade-c';
  if (u.startsWith('D')) return 'grade-d';
  if (u === '**' || u === 'E' || u === 'F') return 'grade-fail';
  return '';
}}

function gpaClass(gpa) {{
  var g = parseFloat(gpa);
  if (isNaN(g)) return '';
  if (g >= 2.5) return 'gpa-high';
  if (g >= 1.5) return 'gpa-mid';
  return 'gpa-low';
}}

function toggleDetails(id) {{
  expanded[id] = !expanded[id];
  render();
}}

function toggleSort() {{
  var modes = ['default', 'gpa-desc', 'gpa-asc', 'name'];
  var labels = ['Default', 'GPA High-Low', 'GPA Low-High', 'Name A-Z'];
  var idx = modes.indexOf(sortMode);
  idx = (idx + 1) % modes.length;
  sortMode = modes[idx];
  document.getElementById('sortBtn').textContent = 'Sort: ' + labels[idx];
  document.getElementById('sortBtn').className = sortMode === 'default' ? 'sort-btn' : 'sort-btn active';
  render();
}}

function render() {{
  var query = document.getElementById('searchInput').value.toLowerCase();
  var filtered = DATA.filter(function(s) {{
    if (!query) return true;
    var text = (s.student_id + ' ' + (s.name_initial||'') + ' ' + (s.full_name||'')).toLowerCase();
    if (text.indexOf(query) >= 0) return true;
    return (s.courses||[]).some(function(c) {{
      return ((c['Course Code']||c['CourseCode']||'')).toLowerCase().indexOf(query) >= 0;
    }});
  }});

  if (sortMode === 'gpa-desc') {{
    filtered.sort(function(a,b) {{ return (parseFloat(b.gpa)||0) - (parseFloat(a.gpa)||0); }});
  }} else if (sortMode === 'gpa-asc') {{
    filtered.sort(function(a,b) {{ return (parseFloat(a.gpa)||0) - (parseFloat(b.gpa)||0); }});
  }} else if (sortMode === 'name') {{
    filtered.sort(function(a,b) {{ return (a.name_initial||'').localeCompare(b.name_initial||''); }});
  }}

  var html = '';
  filtered.forEach(function(s) {{
    var sid = s.student_id;
    if (s.error) {{
      html += '<div class="no-results"><span class="student-id">' + sid + '</span> — No results available</div>';
      return;
    }}
    var isOpen = expanded[sid];
    var gc = gpaClass(s.gpa);
    var courseCount = (s.courses||[]).filter(function(c) {{ return c['Course Code'] && !c['Course Code'].startsWith('Course Code'); }}).length;
    html += '<div class="student-card">';
    html += '<div class="student-header" onclick="toggleDetails(\\'' + sid + '\\')">';
    html += '<div class="student-info"><div class="student-id">' + sid + ' <span class="count-badge">' + courseCount + ' courses</span></div>';
    html += '<div class="student-name">' + (s.name_initial||'N/A') + '</div></div>';
    html += '<div class="student-gpa"><div class="gpa-value ' + gc + '">' + (s.gpa||'N/A') + '</div><div class="gpa-label">GPA</div></div>';
    html += '<div class="toggle-icon' + (isOpen ? ' open' : '') + '">&#9654;</div>';
    html += '</div>';

    if (isOpen) {{
      html += '<div class="student-details open">';
      html += '<p class="detail-meta"><strong>Full Name:</strong> ' + (s.full_name||'') + ' | <strong>Credits:</strong> ' + (s.total_credit||'') + ' | <strong>Non-GPA:</strong> ' + (s.non_gpa_credit||'') + '</p>';
      html += '<table class="course-table"><thead><tr><th>Course Code</th><th>Ac Year</th><th>Attempt</th><th>Exam Status</th><th>Exam Note</th><th>Grade</th></tr></thead><tbody>';
      (s.courses||[]).forEach(function(c) {{
        var code = c['Course Code'] || c['CourseCode'] || '';
        if (code.startsWith('Course Code')) return;
        var grade = c['Grade'] || '';
        var examNote = c['Exam Note'] || c['ExamNote'] || '';
        var examStatus = c['ExamStatus'] || '';
        var absCls = examStatus === 'Absent' ? ' class="absent"' : '';
        html += '<tr><td>' + code + '</td><td>' + (c['AcYear']||'') + '</td><td>' + (c['Attempt']||'') + '</td><td' + absCls + '>' + examStatus + '</td><td>' + examNote + '</td><td class="' + gradeClass(grade) + '">' + grade + '</td></tr>';
      }});
      html += '</tbody></table></div>';
    }}
    html += '</div>';
  }});

  if (filtered.length === 0) {{
    html = '<div style="text-align:center;color:#999;padding:40px;">No students match your search.</div>';
  }}

  document.getElementById('studentList').innerHTML = html;
}}

render();
</script>
</body>
</html>"""
    return html


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_dir = os.path.dirname(script_dir)
    data_file = os.path.join(repo_dir, "data", "results.json")
    html_file = os.path.join(repo_dir, "index.html")

    # Load existing results
    old_results = []
    if os.path.exists(data_file):
        with open(data_file) as f:
            old_results = json.load(f)
        logger.info(f"Loaded {len(old_results)} existing results")

    # Scrape fresh results
    logger.info("Starting scrape of all students...")
    new_results = scrape_all_students()
    logger.info(f"Scraped {len(new_results)} students")

    success_count = len([r for r in new_results if not r.get("error")])
    fail_count = len([r for r in new_results if r.get("error")])
    logger.info(f"Results: {success_count} success, {fail_count} failed/no-data")

    # Detect changes
    newly_available, gpa_changes = detect_changes(old_results, new_results)
    has_changes = len(newly_available) > 0 or len(gpa_changes) > 0

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

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
        logger.info("No changes detected since last scrape")

    # Save new results
    os.makedirs(os.path.dirname(data_file), exist_ok=True)
    with open(data_file, "w") as f:
        json.dump(new_results, f, indent=2)
    logger.info(f"Saved results to {data_file}")

    # Generate HTML
    html = generate_html(new_results, timestamp)
    with open(html_file, "w") as f:
        f.write(html)
    logger.info(f"Generated {html_file}")

    # Set output for GitHub Actions
    github_output = os.environ.get("GITHUB_OUTPUT", "")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"has_changes={'true' if has_changes else 'false'}\n")
            f.write(f"success_count={success_count}\n")
            f.write(f"fail_count={fail_count}\n")
            f.write(f"new_results={len(newly_available)}\n")
            f.write(f"gpa_changes={len(gpa_changes)}\n")

    return has_changes


if __name__ == "__main__":
    try:
        changed = main()
        sys.exit(0 if changed or True else 0)  # Always exit 0
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
