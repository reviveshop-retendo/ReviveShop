#!/usr/bin/env bash
# Build the eShop Music Changer: .3dsx (Homebrew Launcher) and .cia (home menu).
#
# The .cia bundles both the themes (romfs/music/) and the .3dsx itself, so its
# "Install .3dsx" button can copy the launcher build onto the SD card.
# Re-run after changing source or themes.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
SCRATCH=/tmp/opencode/eshop-music-changer-build

export DEVKITPRO=/opt/devkitpro
export DEVKITARM=/opt/devkitpro/devkitARM
export PATH=/opt/devkitpro/tools/bin:$PATH

echo "== staging =="
rm -rf "$SCRATCH"
mkdir -p "$SCRATCH/cia"
cp -r "$ROOT/source" "$ROOT/Makefile" "$SCRATCH/"
cp -r "$ROOT/romfs" "$SCRATCH/romfs"
cp "$ROOT/meta/icon.png" "$SCRATCH/icon.png"

echo "== building .3dsx =="
(
	cd "$SCRATCH"
	make >/dev/null
)
cp "$SCRATCH/eshop_music_changer.3dsx" "$ROOT/eshop_music_changer.3dsx"
echo "   3dsx: $(stat -c%s "$ROOT/eshop_music_changer.3dsx") bytes"

echo "== assembling cia romfs =="
# Themes plus the freshly built .3dsx (so the CIA can reinstall the launcher).
rm -rf "$SCRATCH/cia-romfs"
cp -r "$ROOT/romfs" "$SCRATCH/cia-romfs"
cp "$ROOT/eshop_music_changer.3dsx" "$SCRATCH/cia-romfs/eshop_music_changer.3dsx"
find "$SCRATCH/cia-romfs" -type f | sed 's/^/   /'

echo "== building .cia assets =="
bannertool makebanner \
	-i "$ROOT/meta/banner.png" \
	-a "$ROOT/meta/audio.wav" \
	-o "$SCRATCH/cia/banner.bnr" >/dev/null

bannertool makesmdh \
	-s "eShop Music Changer" \
	-l "Replaces the eShop background music" \
	-p "ReviveShop" \
	-i "$ROOT/meta/icon.png" \
	-o "$SCRATCH/cia/icon.smdh" >/dev/null

echo "== compiling for CIA =="
# MUSIC_CHANGER_CIA drops the theme-install code: an installed app may only
# mount its own extdata, so it cannot write the eShop's archive.  Only the
# .3dsx (run from the Homebrew Launcher) can, and that keeps this flag off.
"$DEVKITARM/bin/arm-none-eabi-gcc" \
	-D__3DS__ -DMUSIC_CHANGER_CIA \
	-march=armv6k -mtune=mpcore -mfloat-abi=hard -mtp=soft \
	-g -Wall -O2 -mword-relocations -ffunction-sections \
	-I"$DEVKITPRO/libctru/include" \
	-c "$ROOT/source/main.c" -o "$SCRATCH/cia/main.o"

# Link with the 3dsx startup so the ELF has a proper ARM11 entry point;
# makerom accepts this ELF directly.
"$DEVKITARM/bin/arm-none-eabi-gcc" -specs=3dsx.specs -g \
	-march=armv6k -mtune=mpcore -mfloat-abi=hard -mtp=soft \
	"$SCRATCH/cia/main.o" \
	-L"$DEVKITPRO/libctru/lib" -lctru -lm \
	-o "$SCRATCH/cia/changer.elf"

echo "== building .cia =="
# RomFS comes from the RSF's "RomFs: RootPath", substituted via -DROMFS_ROOT
# (makerom resolves it against the working directory, not the RSF).
# -desc supplies the access-control/ExHeader template, avoiding the RSF keys
# this makerom build cannot parse.
makerom -f cia -o "$ROOT/eshop_music_changer.cia" \
	-elf "$SCRATCH/cia/changer.elf" \
	-rsf "$ROOT/meta/changer.rsf" \
	"-DROMFS_ROOT=$SCRATCH/cia-romfs" \
	-icon "$SCRATCH/cia/icon.smdh" \
	-banner "$SCRATCH/cia/banner.bnr" \
	-desc app:4 \
	-target t >/dev/null

echo "   cia:  $(stat -c%s "$ROOT/eshop_music_changer.cia") bytes"
echo "== done =="
