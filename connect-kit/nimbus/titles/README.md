# Per-title patches (`/luma/titles/<TID>/code.ips`)

Most ReviveShop redirection is handled at the system-module level (see the
`ssl`, `http`, `act`, `friends` patches). A per-title patch is only needed if a
specific application hard-codes a host that `http:C` never sees, or needs its
own behaviour change.

The main candidate is the **eShop applet** (`0004003000008802` on most retail
consoles; other regions differ). It fetches `ecs.c.shop.nintendowifi.net` /
`ninja.ctr.shop.nintendo.net` through `http:C`, so with the `http` patch it
should already be redirected. Add a title patch here only if testing shows a
host slips through.

## To build one

1. Dump the applet's `code.bin` the same way as a module (GodMode9 → Title
   manager → NAND → open the title folder → `.app` → NCCH image options →
   Extract .code).
2. Create `titles/<TID>/src/main.s` and a `Makefile` (copy one from
   `patches/*/`), open with the applet's `code.bin`.
3. `armips src/main.s && flips -c code.bin build/patched_code.bin out/code.ips`.
4. Install to `sdcard:/luma/titles/<TID>/code.ips`.

The eShop applet is region-specific (JPN/USA/EUR have different title IDs and
slightly different builds), unlike the system modules, so each region may need
its own patch.
