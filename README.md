# University of Kelaniya - Faculty of Science Results

Auto-updating student results dashboard. Scrapes the university website every 6 hours and sends Telegram notifications when new results are detected.

## How It Works

1. **GitHub Actions** runs a scraper every 6 hours (configurable)
2. Scraper checks the university website for all 73 student IDs
3. If new results are found, a **Telegram notification** is sent
4. Updated results are committed to the repo
5. **Vercel** auto-deploys on every push, keeping the site current

## Setup

### 1. Fork/Clone this repo

### 2. Add GitHub Secrets
Go to **Settings > Secrets and variables > Actions** and add:
- `TELEGRAM_BOT_TOKEN` - Your Telegram bot token (from @BotFather)
- `TELEGRAM_CHAT_ID` - Your Telegram chat ID (from @userinfobot)

### 3. Deploy to Vercel
1. Go to [vercel.com](https://vercel.com) and import this GitHub repo
2. Deploy with default settings (no build command needed)
3. Add your custom domain in **Settings > Domains**

### 4. Test
- Click "Run workflow" in GitHub Actions tab to trigger a manual scrape
- Check that your Telegram bot sends a notification if there are changes

## Customization

- **Scrape frequency**: Edit `.github/workflows/scrape.yml` cron schedule
- **Student IDs**: Edit the `STUDENT_IDS` list in `scripts/scrape.py`
