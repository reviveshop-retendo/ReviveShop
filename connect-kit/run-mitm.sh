#!/usr/bin/env bash
# ReviveShop connect kit — run the 3DS rewrite proxy.
#
# Usage:  ./connect-kit/run-mitm.sh [LAN-IP]
# Defaults to this PC's LAN IP (auto-detected) unless an IP is given.
set -euo pipefail

cd "$(dirname "$0")"

LAN_IP="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}')"
: "${LAN_IP:=$(hostname -I 2>/dev/null | awk '{print $1}')}"

# NOTE: do NOT add nus.c.shop.nintendowifi.net to --ignore-hosts. ECS
# GetAccountStatus advertises that exact hostname as NusURL, and the console
# resolves it via its own DNS (the router), landing on a dead real-Nintendo IP
# (198.62.122.164). Ignoring it here means the proxy passes those calls through
# to the dead IP, which stalls ~40s and aborts checkout with 007-2001. rewrite.py
# maps the hostname to this box instead.
RS_SERVER_IP="${1:-$LAN_IP}" .venv-kit/bin/mitmdump \
  --listen-port 8888 --ssl-insecure \
  --set tls_version_client_min=TLS1 \
--set connection_strategy=lazy \
  -s mitmproxy/rewrite.py