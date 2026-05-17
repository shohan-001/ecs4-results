#!/bin/bash
# ============================================
# UoK Results Portal — VPS Setup Script
# Run on your DigitalOcean VPS as root
# ============================================
set -e

echo "========================================="
echo "  UoK Results Portal — VPS Setup"
echo "========================================="

# 1. Install system dependencies
echo "[1/8] Installing dependencies..."
apt update && apt install -y python3 python3-pip python3-venv nginx git

# 2. Create app directory and clone repo
echo "[2/8] Cloning repository..."
rm -rf /opt/results-portal
git clone -b vps-migration https://github.com/shohan-001/ecs4-results.git /opt/results-portal
cd /opt/results-portal

# 3. Python virtual environment
echo "[3/8] Setting up Python environment..."
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 4. Create config.json with real credentials
echo "[4/8] Creating config..."
cat > config.json << 'EOF'
{
  "user_password": "ecs4",
  "admin_password": "ecs4",
  "scrape_interval_minutes": 30,
  "telegram_bot_token": "8757360660:AAEuz4icNP02fNC9-JvLj0LdKW_6la-ssXI",
  "telegram_chat_id": "960178059",
  "base_url": "http://www.science.kln.ac.lk:8080"
}
EOF

# Create empty protected_creds.json
echo '{}' > protected_creds.json

# Create data dirs
mkdir -p data/{ec,ps,pe,ss,bs,ac,em,se}

# Copy existing EC results if available
if [ -f "data/results.json" ]; then
  cp data/results.json data/ec/results.json 2>/dev/null || true
fi

# 5. Nginx config
echo "[5/8] Configuring Nginx..."
cp deploy/nginx-results.conf /etc/nginx/sites-available/results-portal
ln -sf /etc/nginx/sites-available/results-portal /etc/nginx/sites-enabled/results-portal
nginx -t && systemctl reload nginx

# 6. systemd services
echo "[6/8] Setting up systemd services..."
cp deploy/results-portal.service /etc/systemd/system/
cp deploy/results-scraper.service /etc/systemd/system/
cp deploy/results-scraper.timer /etc/systemd/system/
systemctl daemon-reload

# 7. Enable and start
echo "[7/8] Starting services..."
systemctl enable results-portal
systemctl start results-portal
systemctl enable results-scraper.timer
systemctl start results-scraper.timer

# 8. Verify
echo "[8/8] Verifying..."
sleep 2
systemctl status results-portal --no-pager || true
systemctl status results-scraper.timer --no-pager || true

echo ""
echo "========================================="
echo "  SETUP COMPLETE!"
echo "========================================="
echo ""
echo "  Portal:  http://results.iswvoid.me"
echo "  Flask:   http://127.0.0.1:5000"
echo ""
echo "  NEXT STEPS:"
echo "  1. In Cloudflare DNS, add A record:"
echo "     results.iswvoid.me -> 68.183.179.91 (Proxied)"
echo "  2. In Cloudflare SSL/TLS, set mode to 'Flexible'"
echo "  3. Run initial discovery:"
echo "     cd /opt/results-portal && source venv/bin/activate"
echo "     python scripts/scrape.py --discover ec"
echo "     (then discover other depts: ps, pe, ss, bs, ac, em, se)"
echo ""
echo "  USEFUL COMMANDS:"
echo "  systemctl restart results-portal   # Restart Flask"
echo "  systemctl restart results-scraper.timer  # Restart timer"
echo "  journalctl -u results-portal -f    # View Flask logs"
echo "  journalctl -u results-scraper -f   # View scraper logs"
echo "========================================="
