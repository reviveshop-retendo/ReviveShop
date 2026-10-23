#!/usr/bin/env python3
"""Diagnose 3DS eShop traffic from the mitmproxy log.

Reads /tmp/opencode/rs-dev/mitm.log (binary-safe via strings-style scan) and
prints a chronological summary of every request the console made, flagging
errors, missing endpoints, gaps, and CCS misses.

Usage:
  python3 connect-kit/diag.py              # last 5 minutes
  python3 connect-kit/diag.py 15:07        # from timestamp HH:MM today
  python3 connect-kit/diag.py 15:07 15:10  # between two timestamps
  python3 connect-kit/diag.py --purchase   # only purchase-relevant endpoints
"""
import re
import sys
import os

LOG = "/tmp/opencode/rs-dev/mitm.log"

# Endpoints the eShop calls during a purchase flow, in expected order.
PURCHASE_FLOW = [
    "ec_info",
    "tax_location",
    "prepurchase_info",
    "!purchase",
    "ccs/download",  # NUS content download
    "cas/services",  # CAS ListTitlesEx
    "nus/services",  # NetUpdateSOAP
]

# Endpoints we know exist but that should NOT be hit during a normal
# title-page load (they only appear once purchase starts).
PURCHASE_ONLY = ("prepurchase_info", "!purchase")

# Pattern: [HH:MM:SS.mmm][ip:port] event
TS_RE = re.compile(rb"\[(\d{2}:\d{2}:\d{2}\.\d{3})\]")
# [local>PORT] METHOD PATH
LOCAL_RE = re.compile(rb"\[local>(\d+)\]\s+(\S+)\s+(\S+)")
# RESP <body snippet>
RESP_RE = re.compile(rb"^\s*RESP\s+(.*)", re.MULTILINE)
# << STATUS SIZE   e.g. "<< 200 OK 123b"  or "<< 404 NOT FOUND 5b"
STATUS_RE = re.compile(rb"<<\s+(\d{3})\s+(\S+)\s+(\S+)")
# [rewrite](host|ip|...) ... -> ip:port/path
REWRITE_RE = re.compile(rb"\[rewrite\]\((\w+)\)\s+\S+\s*->\s+(\S+)")
# error lines
ERR_RE = re.compile(
    rb"(error establishing|handshake failed|Name or service|"
    rb"CCS MISS|Client disconnected|tlsv1|Connection refused|"
    rb"certificate)", re.IGNORECASE)


def parse_log(start_ts=None, end_ts=None):
    """Yield event dicts from the log within the time window."""
    try:
        raw = open(LOG, "rb").read()
    except OSError as e:
        print(f"Cannot read {LOG}: {e}")
        sys.exit(1)

    # Work on decoded latin-1 so binary bytes don't break regex.
    text = raw.decode("latin-1", errors="replace")

    events = []
    cur_ts = None

    for line in text.splitlines():
        m = TS_RE.search(line.encode("latin-1"))
        if m:
            cur_ts = m.group(1).decode()
            if start_ts and cur_ts < start_ts:
                continue
            if end_ts and cur_ts > end_ts:
                break

        if cur_ts is None:
            continue

        enc = line.encode("latin-1")

        # Local request
        lm = LOCAL_RE.search(enc)
        if lm:
            events.append({
                "ts": cur_ts,
                "kind": "req",
                "port": int(lm.group(1)),
                "method": lm.group(2).decode(),
                "path": lm.group(3).decode(),
            })
            continue

        # Rewrite (shows what the console originally requested)
        rm = REWRITE_RE.search(enc)
        if rm:
            target = rm.group(2).decode()
            events.append({
                "ts": cur_ts,
                "kind": "rewrite",
                "target": target,
            })
            continue

        # Response status
        sm = STATUS_RE.search(enc)
        if sm:
            events.append({
                "ts": cur_ts,
                "kind": "status",
                "code": int(sm.group(1)),
                "reason": sm.group(2).decode(),
                "size": sm.group(3).decode(),
            })
            continue

        # Errors
        if ERR_RE.search(enc):
            events.append({
                "ts": cur_ts,
                "kind": "error",
                "text": line.strip(),
            })
            continue

    return events


def is_interesting_path(path):
    """Filter out asset noise (icons, banners, thumbs)."""
    noise = ("/assets/", "/p01/", "/nppl/", "/npfl/", "/npdl/",
             "/npdi/", "/npts/", "/tagaya/", "ping2", "/outbox/",
             "/inbox/", "/location/")
    p = path.lower()
    return not any(n in p for n in noise)


def gap_flag(prev_ts, cur_ts, threshold=10.0):
    """Return True if gap between two HH:MM:SS.mmm timestamps > threshold s."""
    try:
        h1, m1, s1 = prev_ts.split(":")
        h2, m2, s2 = cur_ts.split(":")
        t1 = int(h1) * 3600 + int(m1) * 60 + float(s1)
        t2 = int(h2) * 3600 + int(m2) * 60 + float(s2)
        return (t2 - t1) > threshold
    except Exception:
        return False


def main():
    args = sys.argv[1:]
    purchase_only = "--purchase" in args
    args = [a for a in args if not a.startswith("--")]

    start_ts = args[0] if len(args) > 0 else None
    end_ts = args[1] if len(args) > 1 else None

    if start_ts is None:
        # Default: last 5 minutes of the log.
        # Find the last timestamp first.
        raw = open(LOG, "rb").read().decode("latin-1", errors="replace")
        all_ts = TS_RE.findall(raw.encode("latin-1"))
        if not all_ts:
            print("No timestamps found in log.")
            return
        last = all_ts[-1].decode()
        h, m, _ = last.split(":")
        total = int(h) * 3600 + int(m) * 60
        total -= 300  # 5 min back
        start_ts = "%02d:%02d" % (total // 3600, (total % 3600) // 60)

    events = parse_log(start_ts, end_ts)

    # Build a merged timeline: pair rewrites with subsequent local requests.
    print(f"=== eShop traffic {start_ts or ''} {end_ts or ''} ===")
    print(f"Window: {start_ts or '(log start)'} .. {end_ts or '(log end)'}")
    print()

    # Track seen endpoints for missing-flow detection.
    seen_paths = []
    purchase_hits = []
    error_lines = []
    last_ts = None
    req_count = 0

    for ev in events:
        if ev["kind"] == "error":
            error_lines.append(ev)
            continue

        if ev["kind"] == "rewrite":
            # Show the original host->path mapping briefly
            pass  # The local> line will follow; skip duplicate.
            continue

        if ev["kind"] == "req":
            path = ev["path"]
            if purchase_only and not is_interesting_path(path):
                continue
            if not is_interesting_path(path) and "/ccs/download" not in path:
                # Still show CCS downloads even if path looks odd.
                if not purchase_only:
                    pass  # Show assets in full mode? No, skip.
                    continue

            req_count += 1
            marker = ""
            if any(p in path for p in PURCHASE_ONLY):
                marker = "  <<< PURCHASE FLOW"
                purchase_hits.append(path)

            gap = ""
            if last_ts and gap_flag(last_ts, ev["ts"], 15.0):
                gap = f"  ** {gap_flag.__defaults__[0]:.0f}s+ GAP — console stalled **"

            print(f"  {ev['ts']}  [{ev['port']}] {ev['method']:6s} {path}{marker}{gap}")
            seen_paths.append(path)
            last_ts = ev["ts"]
            continue

        if ev["kind"] == "status":
            code = ev["code"]
            flag = ""
            if code >= 400:
                flag = "  <<< ERROR"
                error_lines.append(ev)
            elif code == 204:
                flag = "  (204 no content)"
            print(f"  {ev['ts']}  -> {code} {ev['reason']} {ev['size']}{flag}")
            last_ts = ev["ts"]
            continue

    print()
    print("=== DIAGNOSIS ===")
    print(f"Requests in window: {req_count}")

    # Purchase-flow analysis
    if purchase_only or any("tax_location" in p for p in seen_paths):
        print()
        print("Purchase-flow endpoints hit:")
        flow_hit = {name: False for name in
                    ("ec_info", "tax_location", "prepurchase_info",
                     "!purchase", "ccs/download", "cas/services", "nus/services")}
        for p in seen_paths:
            for name in flow_hit:
                if name in p:
                    flow_hit[name] = True
        for name, hit in flow_hit.items():
            status = "YES" if hit else "NO  <<< MISSING"
            print(f"  {name:25s} {status}")
        if flow_hit.get("tax_location") and not flow_hit.get("prepurchase_info"):
            print()
            print("!! tax_location was called but prepurchase_info was NOT.")
            print("   The eShop is failing between these two calls.")
            print("   Check: tax_location response format, session validity.")

    # Errors
    if error_lines:
        print()
        print(f"Errors ({len(error_lines)}):")
        for e in error_lines[-20:]:
            if e["kind"] == "status":
                print(f"  {e['ts']}  HTTP {e['code']} {e['reason']} {e['size']}")
            elif e["kind"] == "error":
                print(f"  {e['ts']}  {e['text'][:120]}")
    else:
        print()
        print("No errors found in window.")

    # Gaps
    print()
    print("Large gaps (>15s) between requests — console may be waiting/hung:")
    gaps = []
    prev = None
    for ev in events:
        if ev["kind"] in ("req", "status"):
            if prev and gap_flag(prev, ev["ts"], 15.0):
                gaps.append((prev, ev["ts"]))
            prev = ev["ts"]
    if gaps:
        for a, b in gaps:
            print(f"  {a} .. {b}")
    else:
        print("  (none)")


if __name__ == "__main__":
    main()
