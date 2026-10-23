#!/bin/sh
# Redirects ONLY one client's (your 3DS) port-443 traffic to our server on 8443.
# Everything else keeps hitting the CurseForge panel that already owns :443.
#
# Usage:
#   sudo sh proxy/setup-redirect.sh            # auto-detect 3DS (Nintendo MAC in ARP table)
#   sudo sh proxy/setup-redirect.sh 192.168.4.77
#
# Power on the 3DS and open the Theme Shop once before auto-detect (so it
# appears in the neighbour table), or pass its IP explicitly.
set -e

TO_PORT="${TO_PORT:-8443}"
CLIENT="${1:-}"

if [ -z "$CLIENT" ]; then
	# Nintendo Co Ltd OUIs (3DS family)
	CLIENT=$(ip neigh show | awk 'BEGIN{IGNORECASE=1}
		/90:b6:86|40:f4:07|8c:cd:e8|2c:cf:67|00:1e:3d|00:21:47|00:23:cc|00:24:1e|00:25:a0|04:03:d6|34:af:2c|58:bd:a3|64:70:02|78:c2:c0|94:58:cb|98:b6:e9|a4:c0:e3|b8:8a:60|d8:6b:f7|e0:0c:7f|e8:68:19/
		{print $1; exit}')
fi

if [ -z "$CLIENT" ]; then
	echo "3DS not found in the neighbour table."
	echo "Power it on, open the Theme Shop once (it may fail — that's fine), then re-run."
	echo "Or pass its IP directly:  sudo sh proxy/setup-redirect.sh <3ds-ip>"
	exit 1
fi

RULE="-s $CLIENT -p tcp --dport 443 -j REDIRECT --to-ports $TO_PORT"

if iptables -t nat -C PREROUTING $RULE 2>/dev/null; then
	echo "Rule already installed for $CLIENT"
else
	iptables -t nat -A PREROUTING $RULE
	echo "Added: redirect $CLIENT:443 -> localhost:$TO_PORT"
fi

echo
iptables -t nat -L PREROUTING -n --line-numbers | head -6
echo
echo "Remove later with:"
echo "  sudo iptables -t nat -D PREROUTING $RULE"
echo
echo "(Rules do not survive reboot — re-run this script after restarting.)"
