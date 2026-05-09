---
name: testing-results-dashboard
description: Test the UoK Science Results PWA dashboard end-to-end. Use when verifying UI changes, PWA features, search/sort/filter functionality, or scraper output.
---

# Testing the Results Dashboard

## Prerequisites
- Python 3 installed (for local HTTP server and scraper)
- Chrome browser available
- Playwright installed (`pip install playwright && playwright install chromium`)

## Local Setup

1. Serve the app locally:
   ```bash
   cd /home/ubuntu/results-app
   python3 -m http.server 8080 &
   ```
2. Open `http://localhost:8080` in Chrome

## Key Test Areas

### 1. Page Load & Summary Stats
- Header: "UoK Science Results" with "Faculty of Science - Year 1 (2023/2024)"
- Summary bar: Total (73), Results (62), Pending (11), Avg GPA (~2.14), Top GPA (2.73)
- Install banner visible at top: "Install this app on your device for quick access"

### 2. Search
- Search by student ID (e.g., "EC/2023/002")
- Search by student name (e.g., "WIMALASURIYA")
- Search by course code (e.g., "ACLT")
- Each should filter to only matching students

### 3. Expandable Cards
- Click a student card to expand course details table
- Verify columns: Course, Year, Att, Status, Note, Grade
- Click again to collapse
- Grades should be color-coded

### 4. Sort
- Sort button cycles: Sort → GPA ↓ → GPA ↑ → Name → Default
- GPA descending: top student should be ~2.73
- Button label changes to indicate current sort mode

### 5. Tab Bar Filters
- Tab bar is mobile-only (CSS media query, hidden on desktop)
- Test programmatically via Playwright or browser console:
  ```js
  showAll();     // Should show 73 (62 .student-card + 11 .no-results)
  showResults(); // Should show 62 (.student-card only)
  showPending(); // Should show 11 (.no-results only)
  ```
- Note: Pending students use `.no-results` class, NOT `.student-card`

### 6. PWA Features
Verify via Playwright or browser DevTools:
- `<link rel="manifest" href="/manifest.json">` exists
- Service Worker registered (`navigator.serviceWorker.getRegistrations()`)
- `<meta name="theme-color" content="#1a73e8">`
- `<meta name="apple-mobile-web-app-capable" content="yes">`
- `<link rel="apple-touch-icon" href="/icon-192.png">`
- Install banner element `#installBanner` exists in DOM

### 7. GitHub Actions Cron
- Verify `.github/workflows/scrape.yml` has `cron: '0 */3 * * *'`

## Programmatic Testing with Playwright

The browser console tool might not work reliably. Use Playwright via CDP instead:
```python
from playwright.sync_api import sync_playwright
p = sync_playwright().start()
browser = p.chromium.connect_over_cdp('http://localhost:29229')
page = browser.contexts[0].pages[0]
page.goto('http://localhost:8080')
# ... run assertions
p.stop()
```

## Known Gotchas
- Vercel preview deployments may return 401 if deployment protection is enabled. Test locally instead.
- PWA install prompt (`beforeinstallprompt`) only fires on HTTPS production deployments, not localhost.
- Tab bar is hidden on desktop viewport via CSS media query — use Playwright to test filter functions programmatically.
- The `generate_html()` function in `scripts/scrape.py` must stay in sync with `index.html`. If you change the template, regenerate index.html.

## Devin Secrets Needed
- `TELEGRAM_BOT_TOKEN` — for testing Telegram notifications (set as GitHub repo secret)
- `TELEGRAM_CHAT_ID` — for testing Telegram notifications (set as GitHub repo secret)
