#!/usr/bin/env bash
# Build ReviveShop Nimbus-style IPS patches.
#
# Prereqs: armips + flips on PATH (or in $RS_TOOLS).
#   armips  https://github.com/Kingcom/armips   (cmake; builds a `armips` binary)
#   flips   https://github.com/Alcaro/Flips     (make TARGET=cli)
#
# For each patch you must place the console's decrypted+decompressed sysmodule
# code binary as <patch>/code.bin (see README "Dumping code.bin").
#
#   ./build.sh http     # regenerate replacements.s, assemble, emit out/code.ips
#   ./build.sh ssl
#   ./build.sh all
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

: "${RS_TOOLS:=}"
[ -n "$RS_TOOLS" ] && export PATH="$RS_TOOLS:$PATH"
for t in armips flips; do
  command -v "$t" >/dev/null || { echo "error: $t not found on PATH (set RS_TOOLS)"; exit 1; }
done

target="${1:-all}"
if [ "$target" = all ]; then
  target="ssl http act friends"
fi

# module title id -> output name
declare -A TID=(
  [ssl]=0004013000002F02
  [http]=0004013000002902
  [act]=0004013000003802
  [friends]=0004013000003202
  [socket]=0004013000002E02
)

for p in $target; do
  dir="patches/$p"
  [ -d "$dir" ] || { echo "error: no such patch '$p'"; exit 1; }
  if [ "$p" = http ]; then
    echo ">> generating redirect table"
    python3 tools/gen_replacements.py
  fi
  if [ ! -f "$dir/code.bin" ]; then
    echo "error: $dir/code.bin missing (dump it from the console first)"; exit 1
  fi
  echo ">> building $p"
  make -C "$dir" --no-print-directory
  mkdir -p out
  name="${TID[$p]:-$p}"
  cp "$dir/out/code.ips" "out/$name.ips"
  echo "   -> out/$name.ips"
done
echo "done."
