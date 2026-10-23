#!/usr/bin/env bash
# ReviveShop dev servers — one-command start/restart.
#
#   ./dev-up.sh          start (or restart) Django, Flask, mitmproxy
#   ./dev-up.sh status   show what's currently running
#
# Logs: /tmp/opencode/rs-dev/{django.log,flask.log,mitm.log}
set -uo pipefail
cd "$(dirname "$0")"

LOG=/tmp/opencode/rs-dev
mkdir -p "$LOG"
CERT="$LOG/cert.pem"
KEY="$LOG/key.pem"

# LAN IP of this PC (the 3DS proxy host). Auto-detected so a DHCP change
# doesn't silently break the rewrite proxy.
LAN_IP="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}')"
: "${LAN_IP:=$(hostname -I 2>/dev/null | awk '{print $1}')}"

# Self-signed dev cert for Django/Flask. Lives in /tmp, so regenerate it after
# every reboot (mitmproxy connects upstream with --ssl-insecure anyway).
if [[ ! -s "$CERT" || ! -s "$KEY" ]]; then
  echo "Generating dev TLS cert for ${LAN_IP}..."
  openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
    -keyout "$KEY" -out "$CERT" -subj "/CN=reviveshop" \
    -addext "subjectAltName=DNS:localhost,IP:${LAN_IP},IP:127.0.0.1" >/dev/null 2>&1
fi

status() {
  for spec in "9000:Django" "8000:Flask" "8888:mitmproxy" "5001:ControlPanel" "8443:ThemeShop"; do
    port="${spec%%:*}"; name="${spec##*:}"
    if ss -tln 2>/dev/null | grep -q ":$port "; then
      echo "  $name  :$port  RUNNING"
    else
      echo "  $name  :$port  down"
    fi
  done
}

if [[ "${1:-}" == "status" ]]; then
  status; exit 0
fi

pkill -f "runserver_plus 0.0.0.0:9000" 2>/dev/null
pkill -f "flask --app main run" 2>/dev/null
pkill -f "mitmdump --listen-port 8888" 2>/dev/null
pkill -f "control-panel/app.py" 2>/dev/null
sleep 1

# Django: ninja metadata + samurai + web admin
setsid nohup .venv/bin/python manage.py runserver_plus 0.0.0.0:9000 \
  --cert-file "$CERT" --key-file "$KEY" > "$LOG/django.log" 2>&1 &

# Flask: ECS/IAS/CAS SOAP + CDN
setsid nohup .venv/bin/python -m flask --app main run -h 0.0.0.0 -p 8000 \
  --cert "$CERT" --key "$KEY" > "$LOG/flask.log" 2>&1 &

# mitmproxy: 3DS -> ReviveShop rewrite proxy (free Charles replacement)
# Do NOT add nus.c.shop.nintendowifi.net to --ignore-hosts: ECS advertises it as
# NusURL, the console resolves it via the router to a dead Nintendo IP, and
# passing it through makes checkout stall ~40s then fail with 007-2001.
setsid nohup env RS_SERVER_IP="$LAN_IP" connect-kit/.venv-kit/bin/mitmdump \
  --listen-port 8888 --ssl-insecure \
  --set tls_version_client_min=TLS1 \
  --set connection_strategy=lazy \
  -s connect-kit/mitmproxy/rewrite.py > "$LOG/mitm.log" 2>&1 &

# Control Panel: the black/red admin UI for 3DS/Wii U/Wii (port 5001)
setsid nohup .venv/bin/python control-panel/app.py > "$LOG/control-panel.log" 2>&1 &

sleep 4
echo "Started. Status:"
status
echo "3DS proxy setting: ${LAN_IP}:8888"
echo "Control Panel:    http://${LAN_IP}:5001/  (admin / admin)"
echo "Logs: $LOG/{django.log,flask.log,mitm.log,control-panel.log}"

# Theme Shop Revival (3DS Theme Shop) on port 8443
# Needs NoSSL Luma patch on console. DNS hijack via arcade-dnsmasq.conf.
pkill -f "theme-shop-revival/server/index.js" 2>/dev/null
setsid nohup env PORT=8443 LAN_IP="$LAN_IP" node theme-shop-revival/server/index.js > "$LOG/themeshop.log" 2>&1 &
echo "Theme Shop:       https://${LAN_IP}:8443/ (NoSSL patch required)"
