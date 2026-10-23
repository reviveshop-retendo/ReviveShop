# eShop Music Changer

A homebrew app (`.3dsx` + `.cia`) that replaces the Nintendo 3DS eShop's
background music by writing the theme into the eShop's own BOSS extdata.

It works **offline** and needs **no SpotPass/StreetPass** — the eShop reads
its theme from local extdata, so once the files are written the shop plays the
new music immediately.

## Downloads

| File | Use |
|---|---|
| `eshop_music_changer.cia` | Install on the home menu (recommended) |
| `eshop_music_changer.3dsx` | Run from the Homebrew Launcher |

Both bundle the same two themes in RomFS.

## Usage

### Which file to run

| If you want to… | Use |
|---|---|
| **Install or restore a theme** | the `.3dsx` via the **Homebrew Launcher** |
| Get the `.3dsx` onto the SD card without a PC | the **CIA**'s *Install .3dsx* button |

The installed **CIA cannot install a theme.** An installed app may only mount
its *own* extdata, and the eShop's music lives in the eShop's archive, so the
mount is refused (`0xE0E046BE`). The Homebrew Launcher runs with enough
privilege to open another title's archive — which is why the `.3dsx` works and
the CIA does not. This is a platform restriction, not a bug.

### Installing a theme (`.3dsx`)

1. **Close the eShop** (it overwrites extdata on exit if left open).
2. Run *eShop Music Changer* from the **Homebrew Launcher**.
3. Choose **Install a theme** → pick:
   - **September_2013**
   - **December_2013**
4. Reopen the eShop. The new music plays.

Choose **Restore original** to put the stock theme back. The original is backed
up to `sdmc:/3ds/eshop_music_changer/backup/` the first time you install a
theme, so restoring always works.

### The CIA

The CIA exists to get the launcher build onto the card: press **Install .3dsx**
and it copies the bundled `.3dsx` to `sdmc:/3ds/eshop_music_changer.3dsx`,
where the Homebrew Launcher scans. Its second menu item explains why it cannot
install a theme itself.

## What it actually does

The eShop keeps its theme in the BOSS extdata archive of title
`0004001000021900`. Two files matter:

| File | Meaning |
|---|---|
| `boss_bgm1` / `boss_bgm3` | the AAC audio |
| `boss_xml1` / `boss_xml3` | header describing the audio + its active date range |

The app opens `ARCHIVE_BOSS_EXTDATA` for that title and overwrites those four
files with the chosen theme's `boss_bgm.aac` / `boss_xml.xml`.

Mounting **another title's** extdata is privileged: 3dbrew notes that regular
apps may only mount SD extdata using their own extdataID. That is the whole
reason the `.3dsx` (Homebrew Launcher) can do this and the installed CIA cannot.
The theme code is compiled out of the CIA build entirely (`MUSIC_CHANGER_CIA`
in `build.sh`), so the CIA ships no broken option.

## Themes

Bundled in `romfs/music/<name>/`, each a pair:

```
boss_bgm.aac    the audio (raw ADTS AAC)
boss_xml.xml    header: version, task, priority, begin/end dates,
                dataSize, loopStartFrame, loopEndFrame
```

The `<dataSize>` in the XML must match the AAC file size, and
`loopEndFrame` controls the loop point. Add a new theme by dropping a folder
with those two files into `romfs/music/` and rebuilding.

## Building

```sh
./build.sh
```

Requires devkitPro (`devkitARM`, `libctru`), `makerom`, and `bannertool`, all
present under `/opt/devkitpro`.

Notes on the build:

- The ELF is linked **with** `3dsx.specs` so it has a proper ARM11 entry point;
  `makerom` accepts that ELF directly.
- The `.3dsx` is built first, then copied into the staged RomFS, so the CIA
  carries both the themes and a copy of the launcher build.
- RomFS is supplied through the RSF's `RomFs: RootPath`, substituted with
  `-DROMFS_ROOT=<abs path>` (makerom resolves the path against the working
  directory, not the RSF).
- `-desc app:4` supplies the access-control/ExHeader template. This avoids
  writing `ServiceAccessControl`/`SystemCallAccess` in the RSF, which this
  makerom build fails to parse (`Unrecognised Key: ''`).

### Reading RomFS from an installed CIA

A `.3dsx` has its RomFS auto-mounted; an installed **CIA does not**. The app
calls `romfsInit()` at startup for that reason. It also never uses `stat()` or
`opendir()` on `romfs:/` paths — RomFS supports `fopen()`, so existence checks
open the file instead, and the theme list is fixed at build time
(`THEME_NAMES[]` in `source/main.c`) rather than enumerated. Using `stat()`
there silently reports every theme as missing.

## Metadata

- Title: **eShop Music Changer**
- Title ID: `000400000DAD0100`
- Product code: `CTR-RSMU`
- Author: ReviveShop

## In the ReviveShop catalogue

The title is published in the shop under **Utilities**, alongside 3hs:

| Piece | Location |
|---|---|
| Title row | `shopdeckdb.Title` id 15, tid `000400000DAD0100` |
| Art | `assetcdn/eshop_music_{112x112,128x128,512x160}.jpg` |
| Installable content | `cdn/000400000dad0100/` (`533516af.app`, `tmd.bin`, `title.tik`) |
| Source CIA | `3ds-media/cias/eShopMusicChanger.cia` |

Imported with `control-panel/backends.py:cia_attach()`, which extracts the real
encrypted content, the real ticket, and a TMD rebuilt to match those bytes
(so the console's hash checks pass). `homebrew_owned()` in `api/views.py` then
materialises an `ownedTitle` row per console, so it downloads like any other
homebrew title — no purchase step.

To re-import after rebuilding:

```sh
cp eshop-music-changer/eshop_music_changer.cia 3ds-media/cias/
.venv/bin/python -c "
import os, django, sys
os.environ.setdefault('DJANGO_SETTINGS_MODULE','reviveshop.settings')
django.setup(); sys.path.insert(0,'control-panel')
import backends; print(backends.cia_attach('eShopMusicChanger.cia'))
"
```

Then run `make_title_art.py` if the art changed.
