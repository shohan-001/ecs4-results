# 🎓 UoK Faculty of Science — Multi-Department Results Portal

A self-hosted, auto-updating student results dashboard for the University of Kelaniya, Faculty of Science. Supports **8 departments**, **~1,380 students**, with smart scraping, Telegram notifications, and a full admin panel.

**Live:** [results.iswvoid.me](https://results.iswvoid.me)

---

## ✨ Features

- **8 Departments** — EC, PS, PE, SS, BS, AC, EM, SE
- **Smart Scraping** — Probes 1 student/dept every 30 min; full scrape only when changes detected
- **Discovery Mode** — Automatically finds real students from ID ranges, skips non-existent accounts
- **Admin Panel** — Manual scrape triggers, interval config, password management
- **Protected Accounts** — Admin can enter passwords for protected students to unlock their results
- **Calculated GPA** — Extracts credits from course codes and computes actual GPA
- **Telegram Alerts** — Instant notifications when new results appear
- **Animated Login** — Ocean-themed glassmorphic UI with waves, bubbles, and shimmer effects
- **PWA Support** — Install as an app on mobile/desktop
- **Per-Department JSON** — Fast lazy-loading, each department loads independently

---

## 🏗️ Architecture

```
Internet → Cloudflare (HTTPS) → Nginx (port 80) → gunicorn/Flask (port 5000)

systemd timer (every 30 min) → scrape.py
  ├── Probe 1 student per department
  ├── If change detected → full scrape that department
  └── Send Telegram notification
```

### Project Structure

```
/opt/results-portal/
├── app.py                      # Flask backend + admin API
├── config.json                 # Credentials & settings (NOT in git)
├── protected_creds.json        # Protected student passwords (NOT in git)
├── requirements.txt
├── scripts/
│   └── scrape.py               # Multi-department scraper
├── static/
│   ├── index.html              # Main HTML
│   ├── styles.css              # All CSS
│   ├── app.js                  # All JavaScript
│   ├── sw.js                   # Service Worker (PWA)
│   ├── manifest.json
│   └── icon-*.png
├── data/
│   ├── ec/results.json         # Per-department results
│   ├── ps/results.json
│   ├── pe/results.json
│   ├── ss/results.json
│   ├── bs/results.json
│   ├── ac/results.json
│   ├── em/results.json
│   ├── se/results.json
│   ├── scrape_state.json       # Last run timestamps
│   └── scrape_status.json      # Live scrape progress
└── deploy/
    ├── setup.sh                # One-command VPS setup
    ├── nginx-results.conf      # Nginx site config
    ├── results-portal.service  # Flask systemd service
    ├── results-scraper.service # Scraper systemd service
    └── results-scraper.timer   # 30-min auto-scrape timer
```

---

## 🚀 VPS Deployment Guide

### Prerequisites

- **DigitalOcean VPS** (or any Ubuntu 24.04 server)
- **Domain** on Cloudflare (e.g., `iswvoid.me`)
- **Telegram Bot** token from [@BotFather](https://t.me/BotFather)

### Step 1: SSH into VPS

```bash
ssh root@YOUR_VPS_IP
```

### Step 2: Run the setup script

```bash
curl -sSL https://raw.githubusercontent.com/shohan-001/ecs4-results/vps-migration/deploy/setup.sh | bash
```

This automatically installs everything: Python, Nginx, Flask, gunicorn, systemd services.

### Step 3: Update config with your credentials

```bash
nano /opt/results-portal/config.json
```

```json
{
  "user_password": "ecs4",
  "admin_password": "your_admin_password",
  "scrape_interval_minutes": 30,
  "telegram_bot_token": "YOUR_BOT_TOKEN",
  "telegram_chat_id": "YOUR_CHAT_ID",
  "base_url": "http://www.science.kln.ac.lk:8080"
}
```

### Step 4: Cloudflare DNS

1. Go to **Cloudflare Dashboard** → your domain → **DNS**
2. Add **A record**:
   - **Name:** `results`
   - **Content:** `YOUR_VPS_IP`
   - **Proxy:** ✅ Proxied (orange cloud)
3. Go to **SSL/TLS** → Set mode to **Flexible**

### Step 5: Discover students

```bash
cd /opt/results-portal
source venv/bin/activate

# Discover each department (finds real students, skips empty IDs)
python scripts/scrape.py --discover ec    # ~90 IDs, ~2 min
python scripts/scrape.py --discover ps    # ~500 IDs, ~15 min
python scripts/scrape.py --discover pe    # ~100 IDs, ~3 min
python scripts/scrape.py --discover ss    # ~70 IDs, ~2 min
python scripts/scrape.py --discover bs    # ~300 IDs, ~10 min
python scripts/scrape.py --discover ac    # ~80 IDs, ~2 min
python scripts/scrape.py --discover em    # ~150 IDs, ~5 min
python scripts/scrape.py --discover se    # ~80 IDs, ~2 min

# OR discover all at once (~30-45 min total):
python scripts/scrape.py --discover all
```

### Step 6: Verify

Visit **https://results.iswvoid.me** — you should see the animated login page.

- **User login:** `ecs4` / `ecs4`
- **Admin login:** Click ⚙️ → `admin` / `ecs4` (change in admin panel after first login)

---

## 🔧 Admin Panel

Access via the ⚙️ button on the department page (requires admin login).

| Feature | Description |
|---------|-------------|
| **Manual Scrape** | Trigger rotation, full scrape, or discovery for any department |
| **Auto-Scrape Interval** | Change from 15 min to 3 hours |
| **Change Passwords** | Update user and admin passwords |
| **Protected Students** | Enter passwords for locked accounts so scraper can access them |
| **Live Status** | See scraper progress in real-time with progress bar |

---

## 📡 Scraper Modes

```bash
cd /opt/results-portal && source venv/bin/activate

# Rotation (default) — probes 1 student per dept, full scrape if change detected
python scripts/scrape.py

# Full scrape — rescrape all known students in a department
python scripts/scrape.py --full ec
python scripts/scrape.py --full all

# Discovery — find new students from ID ranges
python scripts/scrape.py --discover ec
python scripts/scrape.py --discover all
```

---

## 🛠️ Useful Commands

```bash
# Service management
systemctl status results-portal          # Flask app status
systemctl status results-scraper.timer   # Auto-scraper timer status
systemctl restart results-portal         # Restart Flask
systemctl restart results-scraper.timer  # Restart timer

# View logs
journalctl -u results-portal -f         # Flask logs (live)
journalctl -u results-scraper -f        # Scraper logs (live)
journalctl -u results-scraper --since "1 hour ago"  # Recent scraper logs

# Pull code updates
cd /opt/results-portal
git pull origin vps-migration
systemctl restart results-portal
```

---

## 📁 Departments

| Code | Department | ID Range |
|------|-----------|----------|
| EC | Electronics & Computer Science | EC/2023/001–084 |
| PS | Physical Science | PS/2023/001–500 |
| PE | Physics & Electronics | PE/2023/001–100 |
| SS | Sport Science | SS/2023/001–070 |
| BS | Biological Science | BS/2023/001–300 |
| AC | Applied Chemistry | AC/2023/001–080 |
| EM | Environmental Management | EM/2023/001–150 |
| SE | Software Engineering | SE/2023/001–080 |

---

## 🔀 Branches

| Branch | Purpose |
|--------|---------|
| `main` | Original Vercel + GitHub Actions setup (backup) |
| `vps-migration` | Current VPS-based multi-department portal |

---

## ⚠️ Legacy Setup (main branch)

The `main` branch contains the original single-department setup using:
- **Vercel** for hosting
- **GitHub Actions** for scraping (every 30 min)
- Only ECS department (73 students)

This is kept as a backup. The active deployment uses the `vps-migration` branch.
