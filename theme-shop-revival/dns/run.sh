#!/bin/sh
# Starts the Theme Shop Revival DNS server (creates its venv on first run).
set -e
cd "$(dirname "$0")"

if [ ! -d venv ]; then
	python3 -m venv venv
	venv/bin/pip install --quiet dnslib
fi

exec venv/bin/python -u server.py "$@"
