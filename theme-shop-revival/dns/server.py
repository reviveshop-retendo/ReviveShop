#!/usr/bin/env python3
"""Theme Shop Revival DNS server.

Resolves the Nintendo Theme Shop hostnames to your server's LAN IP and
forwards every other query to a real upstream resolver (so a 3DS pointed
at this DNS keeps working for everything else).

Usage:
  sudo python3 dns/server.py                 # port 53, auto-detect LAN IP
  python3 dns/server.py --port 5353 --ip 192.168.1.50
"""

import argparse
import socket
import sys

from dnslib import A, DNSHeader, DNSRecord, QTYPE, RR
from dnslib.server import BaseResolver, DNSLogger, DNSServer

HIJACK_HOSTS = {
    "npdl.cdn.nintendowifi.net",
    "npfl.c.app.nintendowifi.net",
    "nppl.c.app.nintendowifi.net",
}


def detect_lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()


class Resolver(BaseResolver):
    def __init__(self, target_ip: str, upstream: str):
        self.target_ip = target_ip
        self.upstream = upstream

    def resolve(self, request: DNSRecord, handler):
        q = request.q
        qname = str(q.qname).rstrip(".")
        qtype = QTYPE[q.qtype]

        if qname in HIJACK_HOSTS and q.qtype == QTYPE.A:
            reply = request.reply()
            reply.add_answer(
                RR(qname, QTYPE.A, rdata=A(self.target_ip), ttl=60)
            )
            print(f"A {qname} -> {self.target_ip}")
            return reply

        if qname in HIJACK_HOSTS:
            # Not IPv4: answer empty NOERROR so clients don't hang/retry
            reply = DNSRecord(
                DNSHeader(id=request.header.id, qr=1, aa=0, ra=1),
                q=q,
            )
            print(f"{qtype} {qname} -> empty (hijacked host, A only)")
            return reply

        # Forward everything else upstream
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(3.0)
        try:
            sock.sendto(request.pack(), (self.upstream, 53))
            data, _ = sock.recvfrom(4096)
            return DNSRecord.parse(data)
        except OSError as e:
            print(f"upstream error for {qname}: {e}", file=sys.stderr)
            reply = request.reply()
            return reply
        finally:
            sock.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ip", default=None, help="LAN IP to answer for shop hosts")
    ap.add_argument("--port", type=int, default=53, help="UDP port (default 53)")
    ap.add_argument("--upstream", default="8.8.8.8", help="forwarder (default 8.8.8.8)")
    ap.add_argument("--bind", default="0.0.0.0", help="bind address")
    args = ap.parse_args()

    target_ip = args.ip or detect_lan_ip()
    resolver = Resolver(target_ip, args.upstream)
    server = DNSServer(resolver, port=args.port, address=args.bind, logger=DNSLogger("request,reply"))
    print(f"Theme Shop Revival DNS on {args.bind}:{args.port}")
    print(f"  hijack: {', '.join(sorted(HIJACK_HOSTS))} -> {target_ip}")
    print(f"  upstream: {args.upstream}")
    try:
        server.start()
    except PermissionError:
        print(f"Permission denied on port {args.port} — re-run with sudo or --port 5353", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
