# Theme Shop Revival — Setup Guide

Self-hosted 3DS Theme Shop server. Two ways to connect: **DNS (recommended)** or **proxy (fallback)**.

> ⚠️ Both modes require the **NoSSL Luma patch** on your 3DS. The Theme Shop speaks HTTPS
> with Nintendo's certificate chain; without the patch your console rejects our self-signed
> certificate. DNS alone cannot bypass certificate validation.

---

## 0. Quick start — this specific PC (dnsmasq + CurseForge panel already running)

This machine already runs **dnsmasq** (the LAN resolver, `udp/53`) and a
**CurseForge panel** (root `node index.js`, ports 80/443). Don't fight them:

```sh
cd ~/theme-shop-revival

# 1) DNS: add our 3 hijacked hostnames to the existing dnsmasq (not dns/run.sh!)
sudo cp dns/dnsmasq-theme-shop.conf /etc/dnsmasq.d/04-themeshop.conf
sudo systemctl restart dnsmasq

# 2) HTTPS on 8443 — no sudo needed (443 belongs to the CurseForge panel)
PORT=8443 npm start

# 3) In another terminal: redirect ONLY the 3DS's :443 traffic to 8443,
#    so the CurseForge panel keeps serving everyone else.
#    (Power on the 3DS + open the shop once first, so it shows up in ARP.)
sudo sh proxy/setup-redirect.sh          # or: sudo sh proxy/setup-redirect.sh <3ds-ip>
```

Then set the 3DS DNS to `192.168.4.34` (step 3 below) and open the Theme Shop.

Notes:
- `dns/run.sh` is **not** used on this machine — dnsmasq owns port 53. It's
  kept for other hosts without an existing DNS server.
- The redirect rule does not survive a reboot — re-run `setup-redirect.sh`.
- To see every hostname the 3DS looks up (find hosts we still need to hijack):
  add `log-queries` to the drop-in, `sudo systemctl restart dnsmasq`, then
  `sudo journalctl -u dnsmasq -f`.

---

## 1. Console prep (once)

1. Get the NoSSL patch from the [Pretendo Nimbus releases](https://github.com/PretendoNetwork/Nimbus/releases)
   (zip contains `update/0004013000002F02.ips` — that's the SSL sysmodule patch).
2. Copy it to your SD card as:
   ```
   sd:/luma/sysmodules/0004013000002F02.ips
   ```
3. Hold **SELECT** while powering on → enable:
   - `Enable loading external FIRMs and modules`
   - `Enable game patching`
   - Press START to save.
4. Remove the patch when you're done (`sd:/luma/sysmodules/0004013000002F02.ips`) —
   with it installed, all HTTPS on the console (e.g. browser) is unprotected.

## 2. Server setup (on your PC)

```sh
cd theme-shop-revival
npm install               # already done if you cloned with deps
npm run extract-key       # reads ~/3ds/boot9.bin → data/.env (BOSS AES key)
npm run gen-certs         # self-signed certs for the 3 shop hostnames
sudo npm start            # HTTPS on port 443 (or PORT=8443 + iptables, see below)
```

Port 443 needs root. Alternatives:

```sh
# a) just run as root (simplest)
sudo npm start

# b) cap the node binary instead (no root per-run)
sudo setcap 'cap_net_bind_service=+ep' "$(readlink -f "$(which node)")"
npm start

# c) high port + scoped redirect — if something already owns 443 (a panel, etc.)
#    Only the 3DS's traffic is redirected; everything else keeps hitting the
#    existing service. Do NOT use an unscoped PREROUTING rule — it would steal
#    port 443 from every LAN client.
PORT=8443 npm start &
sudo sh proxy/setup-redirect.sh <3ds-ip>
```

Firewall: allow inbound **tcp/443** and **udp/53** (DNS mode).

## 3. DNS mode (recommended)

**On this PC:** skip this section — use the dnsmasq drop-in from section 0.

**On a machine without an existing DNS server:**

```sh
sudo sh dns/run.sh                 # auto-detects your LAN IP, listens on udp/53
# test first without root:
sh dns/run.sh --port 5353
```

On the 3DS: **System Settings → Internet Settings → Connection Settings →
[your connection] → Change Settings → DNS → Manual**

- Primary DNS: `<your PC's LAN IP>` (the IP the DNS script prints)
- Secondary DNS: leave empty or `0.0.0.0` — everything else is forwarded to
  `8.8.8.8`, so normal internet keeps working

Save, run a connection test, then open the Theme Shop.

## 4. Proxy mode (fallback)

Use Pretendo's capture proxy: follow the
[`mitmproxy-nintendo`](https://github.com/PretendoNetwork/mitmproxy-nintendo)
README for 3DS (port 8083, NoSSL patch as above), then either:

- run our server behind it with a redirect script in `proxy/`, or
- keep using DNS mode — the NoSSL patch makes DNS mode the simpler path anyway.

## 5. Logs & debugging

- Every request the console makes lands in `data/logs/requests.jsonl`
  (headers + base64 body) — this is our reverse-engineering feed.
- `TLS error from ...` lines in the server console = handshake rejected;
  check the NoSSL patch is actually loaded (Luma flags!) and that the 3DS
  firmware isn't newer than the patch.
- Unknown/404 paths in the log = route we haven't implemented yet —
  report them, they define what still needs reverse-engineering.

## 6. Removing everything

1. Delete `sd:/luma/sysmodules/0004013000002F02.ips`
2. Set the 3DS connection DNS back to **Automatic**
3. Delete `data/certs/` if you want certs regenerated later
