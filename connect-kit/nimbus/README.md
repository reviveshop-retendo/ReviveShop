# ReviveShop Nimbus-style 3DS patches

Drop-on-SD patches that make a 3DS talk to the local ReviveShop servers **with
no proxy setting and no certificate installed on the console**. This is the
same technique [Pretendo's Nimbus](https://github.com/PretendoNetwork/nimbus)
uses.

## How it works (Nimbus mechanism)

Luma3DS can patch system modules and titles at boot using **IPS patches**:

| File on SD card | Patches |
| --- | --- |
| `/luma/sysmodules/<TID>.ips` | a system module |
| `/luma/titles/<TID>/code.ips` | an installed title (e.g. the eShop applet) |

Luma3DS requires *Enable game patching* on at boot.

Patches are built with two tools:

* **armips** — assembles ARM assembly into a copy of the module's `code.bin`.
* **flips** — diffs the original `code.bin` against the patched one and writes
  the `.ips`.

Nimbus redirects Nintendo hostnames at the string level inside the **`http:C`**
system module (every HTTP/HTTPS request the console makes funnels through it),
and disables certificate verification in the **`SSL`** module. Because the
redirect happens in the OS, the console's Internet Settings stay untouched.

## What this set redirects

`hosts.conf` maps the Nintendo/BOSS/eShop hosts onto the ReviveShop box as
`IP:PORT`, e.g.:

```
ecs.c.shop.nintendowifi.net    -> 192.168.4.34:8000   (Flask: ECS/IAS/CAS + CDN)
ninja.ctr.shop.nintendo.net    -> 192.168.4.34:9000   (Django: Ninja metadata)
nasc.nintendowifi.net          -> 192.168.4.34:59400   (Badge Arcade NEX auth)
```

Because the port is baked into the replacement there is **no DNS override and
no reverse proxy needed** — the console connects straight to the box.

## Two ways to do the redirect

1. **Host → `IP:PORT`** (what's implemented here). Simplest, fully local, no
   DNS. Needs the IP to be stable (set a DHCP reservation for the box).
2. **Host suffix → your own hostname** (the Nimbus way). Requires you to own a
   hostname + DNS; only worth it if the box is reachable from outside.

## Dumping `code.bin` (required before building)

Each module's original code is needed. On a hacked 3DS, the easy way is the
Nimbus module-extractor script:

1. Download `dump_modules.gm9` from
   <https://github.com/TraceEntertains/nimbus-module-extractor/releases>.
2. Put it in `sdcard:/gm9/scripts/`.
3. Boot **GodMode9** → **Home** → **Scripts** → `dump_modules.gm9`.
4. Power off, pull the SD card, and copy the `patches/` folder it produced
   (`sdcard:/nimbusmodules/patches/`) into this directory (merge).

Or manually: GodMode9 → **Home** → *Title manager* → **NAND / TWL** → open the
module → **A** on the `.app` → *NCCH image options* → **Extract .code**. The
result is `0:/gm9/out/<TitleID>.dec.code`; rename it to `code.bin` in the
matching `patches/<name>/` folder.

Module title IDs:

| Patch | Module | Title ID |
| --- | --- | --- |
| ssl | SSL | `0004013000002F02` |
| http | HTTP (http:C) | `0004013000002902` |
| act | Account | `0004013000003802` |
| friends | Friends (frd) | `0004013000003202` |

> The manual offsets assume the common retail layout (same as Nimbus). If a
> module build differs, tell me and I'll re-anchor.

## Server side

The `http` patch rewrites requests straight to the box, so the box must answer
everything the mitmproxy addon used to. Most of it is already served by the
Flask/Django apps; the one piece the proxy used to **fabricate inline** was
NASC, so `nasc.py` was added (registered in `main.py`, served on Flask `:8000`
at `/ac/`).

## Build

```bash
export RS_TOOLS=/home/wiiugamepad/.local/bin   # armips + flips
./build.sh all     # ssl http act friends -> out/<TitleID>.ips
```

Or for a single patch: `cd patches/http && make` (needs `code.bin` present).

## Install on the 3DS

```
sdcard:/luma/sysmodules/0004013000002F02.ips   # SSL (no cert verification)
sdcard:/luma/sysmodules/0004013000002902.ips   # http:C host redirect
sdcard:/luma/sysmodules/0004013000003802.ips   # act account URL
sdcard:/luma/sysmodules/0004013000003202.ips   # friends NASC URL
```

Reboot the 3DS while holding **SELECT** and ensure both
*Enable loading external FIRMs and modules* and *Enable game patching* are on.
Then launch the eShop — no proxy, no cert install.

## Important reality check

* **GitHub cannot host the game servers.** GitHub Pages serves static files
  only; Actions runners are ephemeral and using them as a server violates
  GitHub's terms. The ReviveShop/Retendo servers must run on the box (or a VPS)
  with real open ports. GitHub can only host the *website*.
* The box's IP must be reachable from the 3DS on the same LAN (it is, via Wi-Fi).

## Status

* `ssl` — built and **verified byte-identical** to the shipped
  `connect-kit/0004013000002F02.ips`.
* `http` — source + generator complete; assembles and emits an IPS.
* `act`, `friends` — built; kept as belt-and-braces (http:C normally covers
  them). Offsets are the common retail layout, untested on hardware.
* All four need the real `code.bin` files to produce deployable patches and a
  hardware test.
* Next: test SSL + http:C on the console; then per-title eShop applet patch if
  a host slips through (see `titles/`). Theme Shop revival comes after.

## Credit

Patch structures adapted from **PretendoNetwork/nimbus** (MIT) and
**TraceEntertains/3DS-SSL-Patch**. Shared under the same terms.
