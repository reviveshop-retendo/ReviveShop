/*
 * ReviveShop eShop Music Changer
 *
 * Replaces the Nintendo 3DS eShop background music by writing the BOSS
 * payload files (boss_bgm1 + boss_xml1, and the boss_bgm3/boss_xml3 pair)
 * into the eShop's BOSS extdata archive.
 *
 * The eShop reads its theme from its own extdata, not from the network, so
 * this works entirely offline and does not need SpotPass enabled.
 *
 * Themes are bundled in the CIA's RomFS under /music/<name>/ as
 * boss_bgm.aac + boss_xml.xml.  Original files are backed up to SD before
 * being overwritten so the stock theme can be restored.
 */

#include <3ds.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>

/* ------------------------------------------------------------------ */
/* Configuration                                                       */
/* ------------------------------------------------------------------ */

/* The eShop (USA) title id.  Its BOSS extdata holds the shop theme. */
#define ESHOP_TITLE_ID      0x0004001000021900ULL

/* Files written inside the eShop BOSS extdata. */
#define EXT_BGM1            "/boss_bgm1"
#define EXT_XML1            "/boss_xml1"
#define EXT_BGM3            "/boss_bgm3"
#define EXT_XML3            "/boss_xml3"

/* Where the bundled themes live in RomFS. */
#define ROMFS_MUSIC_DIR     "romfs:/music"

/* Backups of the stock theme, kept on the SD card. */
#define SD_BACKUP_DIR       "sdmc:/3ds/eshop_music_changer/backup"
#define SD_BGM1_BAK         SD_BACKUP_DIR "/boss_bgm1.aac"
#define SD_XML1_BAK         SD_BACKUP_DIR "/boss_xml1.xml"
#define SD_BGM3_BAK         SD_BACKUP_DIR "/boss_bgm3.aac"
#define SD_XML3_BAK         SD_BACKUP_DIR "/boss_xml3.xml"

#define IO_CHUNK            65536

/* ------------------------------------------------------------------ */
/* Small helpers                                                       */
/* ------------------------------------------------------------------ */

/*
 * Test whether a path can be opened.
 *
 * stat() does not work on RomFS paths in libctru (RomFS supports open/read,
 * not stat), so existence is checked by trying to open the file.
 */
static bool file_exists(const char *path)
{
	FILE *f = fopen(path, "rb");
	if (!f) return false;
	fclose(f);
	return true;
}

/* Copy a whole file.  Returns 0 on success. */
static int copy_path(const char *src, const char *dst)
{
	FILE *in = fopen(src, "rb");
	if (!in) return -1;

	FILE *out = fopen(dst, "wb");
	if (!out) { fclose(in); return -2; }

	u8 *buf = (u8 *)malloc(IO_CHUNK);
	if (!buf) { fclose(in); fclose(out); return -3; }

	int rc = 0;
	size_t n;
	while ((n = fread(buf, 1, IO_CHUNK, in)) > 0) {
		if (fwrite(buf, 1, n, out) != n) { rc = -4; break; }
	}
	if (ferror(in)) rc = -5;

	free(buf);
	fclose(in);
	fclose(out);
	return rc;
}

#ifndef MUSIC_CHANGER_CIA
static void ensure_backup_dir(void)
{
	mkdir("sdmc:/3ds", 0777);
	mkdir("sdmc:/3ds/eshop_music_changer", 0777);
	mkdir(SD_BACKUP_DIR, 0777);
}

/* ------------------------------------------------------------------ */
/* Extdata access                                                      */
/* ------------------------------------------------------------------ */

/*
 * Open the eShop BOSS extdata archive.
 *
 * ARCHIVE_BOSS_EXTDATA takes an FS_ExtSaveDataInfo describing which title's
 * extdata we want.  saveId is the low 32 bits of the title id.
 */
static Result open_boss_extdata(FS_Archive *archive)
{
	FS_ExtSaveDataInfo info;
	memset(&info, 0, sizeof info);
	info.mediaType = MEDIATYPE_SD;
	info.saveId    = (u32)(ESHOP_TITLE_ID & 0xFFFFFFFFULL);

	/* Path type 2 == binary blob, meaning is per-archive. */
	FS_Path path;
	path.type = PATH_BINARY;
	path.size = sizeof info;
	path.data = &info;

	return FSUSER_OpenArchive(archive, ARCHIVE_BOSS_EXTDATA, path);
}

/* Copy an extdata file out to an SD path. Returns 0 on success. */
static int read_from_archive(FS_Archive archive, const char *name,
                             const char *sd_dst)
{
	Handle file;
	Result rc = FSUSER_OpenFile(&file, archive,
	                            fsMakePath(PATH_ASCII, name),
	                            FS_OPEN_READ, 0);
	if (R_FAILED(rc)) return -1;

	FILE *out = fopen(sd_dst, "wb");
	if (!out) { FSFILE_Close(file); return -2; }

	u8 *buf = (u8 *)malloc(IO_CHUNK);
	if (!buf) { fclose(out); FSFILE_Close(file); return -3; }

	u64 offset = 0;
	int rv = 0;
	for (;;) {
		u32 read = 0;
		rc = FSFILE_Read(file, &read, offset, buf, IO_CHUNK);
		if (R_FAILED(rc)) { rv = -4; break; }
		if (read == 0) break;
		if (fwrite(buf, 1, read, out) != read) { rv = -5; break; }
		offset += read;
	}

	free(buf);
	fclose(out);
	FSFILE_Close(file);
	return rv;
}

/* Write a SD file into the opened archive at 'name'. Returns 0 on success. */
static int write_to_archive(FS_Archive archive, const char *name,
                            const char *sd_src)
{
	Handle file;
	Result rc = FSUSER_OpenFile(&file, archive,
	                            fsMakePath(PATH_ASCII, name),
	                            FS_OPEN_WRITE | FS_OPEN_CREATE, 0);
	if (R_FAILED(rc)) return -1;

	FILE *in = fopen(sd_src, "rb");
	if (!in) { FSFILE_Close(file); return -2; }

	u8 *buf = (u8 *)malloc(IO_CHUNK);
	if (!buf) { fclose(in); FSFILE_Close(file); return -3; }

	u64 offset = 0;
	int rv = 0;
	size_t n;
	while ((n = fread(buf, 1, IO_CHUNK, in)) > 0) {
		u32 written = 0;
		rc = FSFILE_Write(file, &written, offset, buf, (u32)n,
		                  FS_WRITE_FLUSH);
		if (R_FAILED(rc) || written != n) { rv = -4; break; }
		offset += written;
	}
	if (ferror(in)) rv = -5;

	/* Shrink the file to what we actually wrote. */
	if (rv == 0) FSFILE_SetSize(file, offset);

	free(buf);
	fclose(in);
	FSFILE_Close(file);
	return rv;
}

/* ------------------------------------------------------------------ */
/* Theme install / restore                                             */
/* ------------------------------------------------------------------ */

/*
 * Install a theme.
 *
 *   1. back up the stock extdata files to SD (once)
 *   2. write the chosen boss_bgm.aac / boss_xml.xml into extdata slots 1 and 3
 *
 * Returns 0 on success.
 *
 * Only built for the .3dsx target: the Homebrew Launcher holds the privilege
 * needed to mount another title's extdata.  The installed CIA cannot, so this
 * code is omitted there (MUSIC_CHANGER_CIA) rather than shipped broken.
 */
static int install_theme(const char *theme_name)
{
	char bgm_src[256], xml_src[256];
	snprintf(bgm_src, sizeof bgm_src, ROMFS_MUSIC_DIR "/%s/boss_bgm.aac", theme_name);
	snprintf(xml_src, sizeof xml_src, ROMFS_MUSIC_DIR "/%s/boss_xml.xml", theme_name);

	if (!file_exists(bgm_src) || !file_exists(xml_src)) {
		printf("  Theme '%s' is missing boss_bgm.aac or boss_xml.xml.\n", theme_name);
		return -1;
	}

	FS_Archive archive;
	Result rc = open_boss_extdata(&archive);
	if (R_FAILED(rc)) {
		printf("  Could not open the eShop extdata archive.\n");
		printf("  Is the eShop closed?  (rc=0x%08lX)\n", (unsigned long)rc);
		return -2;
	}

	ensure_backup_dir();

	/* Pull the live extdata down to SD so it can be restored later. */
	char tmp[256];
	snprintf(tmp, sizeof tmp, "sdmc:/3ds/eshop_music_changer/tmp_bgm1");
	char tmp_xml[256];
	snprintf(tmp_xml, sizeof tmp_xml, "sdmc:/3ds/eshop_music_changer/tmp_xml1");

	if (!file_exists(SD_BGM1_BAK)) {
		printf("  Backing up the stock theme...\n");
		if (read_from_archive(archive, EXT_BGM1, tmp) == 0 &&
		    read_from_archive(archive, EXT_XML1, tmp_xml) == 0) {
			rename(tmp, SD_BGM1_BAK);
			rename(tmp_xml, SD_XML1_BAK);
			/* The 3 slots are normally identical; reuse as the slot-3 backup. */
			copy_path(SD_BGM1_BAK, SD_BGM3_BAK);
			copy_path(SD_XML1_BAK, SD_XML3_BAK);
			printf("  Backup saved.\n");
		} else {
			printf("  Warning: could not back up the stock theme.\n");
		}
		remove(tmp);
		remove(tmp_xml);
	} else {
		printf("  Existing backup found, keeping it.\n");
	}

	printf("  Writing boss_bgm ...\n");
	if (write_to_archive(archive, EXT_BGM1, bgm_src) != 0 ||
	    write_to_archive(archive, EXT_BGM3, bgm_src) != 0) {
		printf("  Failed to write boss_bgm.\n");
		FSUSER_CloseArchive(archive);
		return -3;
	}

	printf("  Writing boss_xml ...\n");
	if (write_to_archive(archive, EXT_XML1, xml_src) != 0 ||
	    write_to_archive(archive, EXT_XML3, xml_src) != 0) {
		printf("  Failed to write boss_xml.\n");
		FSUSER_CloseArchive(archive);
		return -4;
	}

	FSUSER_CloseArchive(archive);
	printf("  Done.  Open the eShop to hear it.\n");
	return 0;
}
#endif /* !MUSIC_CHANGER_CIA -- theme install */

/* ------------------------------------------------------------------ */
/* Homebrew Launcher payload                                           */
/* ------------------------------------------------------------------ */

/*
 * Copy the bundled .3dsx onto the SD card so the Homebrew Launcher can run
 * it.  The launcher scans sdmc:/3ds/, so the file is written there with the
 * same name this CIA was built from.
 *
 * Only the installed CIA offers this (it is how you get the launcher build
 * onto the card); the .3dsx build is already the launcher build.
 */
#ifdef MUSIC_CHANGER_CIA
static int install_3dsx(void)
{
	/* The build puts the launcher build at this fixed RomFS path. */
	static const char *SRC = "romfs:/eshop_music_changer.3dsx";
	static const char *DST = "sdmc:/3ds/eshop_music_changer.3dsx";

	if (!file_exists(SRC)) {
		printf("  This CIA was built without the bundled .3dsx.\n");
		return -1;
	}

	printf("  Writing %s ...\n", DST);
	mkdir("sdmc:/3ds", 0777);

	int rc = copy_path(SRC, DST);
	if (rc != 0) {
		printf("  Failed to write the file (error %d).\n", rc);
		printf("  Is the SD card writable?\n");
		return rc;
	}

	printf("  Installed.\n");
	printf("\n  Open the Homebrew Launcher and run\n");
	printf("  'eShop Music Changer'.\n");
	return 0;
}
#endif /* MUSIC_CHANGER_CIA -- install_3dsx */

#ifndef MUSIC_CHANGER_CIA
/* Restore the stock theme from the SD backups. */
static int restore_theme(void)
{
	if (!file_exists(SD_BGM1_BAK) || !file_exists(SD_XML1_BAK)) {
		printf("  No backup found, nothing to restore.\n");
		return -1;
	}

	FS_Archive archive;
	Result rc = open_boss_extdata(&archive);
	if (R_FAILED(rc)) {
		printf("  Could not open the eShop extdata archive (rc=0x%08lX).\n",
		       (unsigned long)rc);
		return -2;
	}

	printf("  Restoring boss_bgm ...\n");
	if (write_to_archive(archive, EXT_BGM1, SD_BGM1_BAK) != 0 ||
	    write_to_archive(archive, EXT_BGM3, SD_BGM3_BAK) != 0) {
		printf("  Failed to restore boss_bgm.\n");
		FSUSER_CloseArchive(archive);
		return -3;
	}

	printf("  Restoring boss_xml ...\n");
	if (write_to_archive(archive, EXT_XML1, SD_XML1_BAK) != 0 ||
	    write_to_archive(archive, EXT_XML3, SD_XML3_BAK) != 0) {
		printf("  Failed to restore boss_xml.\n");
		FSUSER_CloseArchive(archive);
		return -4;
	}

	FSUSER_CloseArchive(archive);
	printf("  Original theme restored.\n");
	return 0;
}
#endif /* !MUSIC_CHANGER_CIA */

/* ------------------------------------------------------------------ */
/* Themes bundled in RomFS                                             */
/* ------------------------------------------------------------------ */

#ifndef MUSIC_CHANGER_CIA
/*
 * The theme list is fixed at build time. Enumerating RomFS with opendir is
 * fragile (and RomFS is not auto-mounted for an installed CIA), so the names
 * are baked in and probed individually with fopen().
 */
static const char *THEME_NAMES[] = {
	"December_2013",
	"September_2013",
};

#define THEME_COUNT ((int)(sizeof THEME_NAMES / sizeof THEME_NAMES[0]))

static char theme_names[THEME_COUNT][128];
static int  theme_count = 0;

static void scan_themes(void)
{
	theme_count = 0;
	for (int i = 0; i < THEME_COUNT; i++) {
		char probe[320];
		snprintf(probe, sizeof probe, ROMFS_MUSIC_DIR "/%s/boss_bgm.aac",
		         THEME_NAMES[i]);
		if (!file_exists(probe)) continue;
		snprintf(theme_names[theme_count], sizeof theme_names[0], "%s",
		         THEME_NAMES[i]);
		theme_count++;
	}
}
#endif /* !MUSIC_CHANGER_CIA */

/* ------------------------------------------------------------------ */
/* UI                                                                  */
/* ------------------------------------------------------------------ */

#define TOP_SCREEN 0
#define BOT_SCREEN 1

static void draw_header(const char *subtitle)
{
	printf("\x1b[2J\x1b[1;1H");
	printf("\x1b[1;37m  ReviveShop eShop Music Changer\x1b[0m\n");
	printf("  \x1b[0;37m--------------------------------------------\x1b[0m\n");
	if (subtitle) printf("  %s\n", subtitle);
	printf("\n");
}

#ifndef MUSIC_CHANGER_CIA
static void draw_menu(int cursor)
{
	draw_header("Select an option:");
	printf("   \x1b[%s%s\x1b[0m\n", cursor == 0 ? "7;37m> " : "0;37m  ",
	       "[ Install a theme ]");
	printf("   \x1b[%s%s\x1b[0m\n", cursor == 1 ? "7;37m> " : "0;37m  ",
	       "[ Restore original ]");
	printf("   \x1b[%s%s\x1b[0m\n", cursor == 2 ? "7;37m> " : "0;37m  ",
	       "[ Exit ]");
	printf("\n\n   \x1b[0;37mUp/Down to move   A to select\x1b[0m\n");
}
#else
static void draw_menu(int cursor)
{
	draw_header("Select an option:");
	printf("   \x1b[%s%s\x1b[0m\n", cursor == 0 ? "7;37m> " : "0;37m  ",
	       "[ Install .3dsx ]");
	printf("   \x1b[%s%s\x1b[0m\n", cursor == 1 ? "7;37m> " : "0;37m  ",
	       "[ Why can't this install a theme? ]");
	printf("   \x1b[%s%s\x1b[0m\n", cursor == 2 ? "7;37m> " : "0;37m  ",
	       "[ Exit ]");
	printf("\n\n   \x1b[0;37mUp/Down to move   A to select\x1b[0m\n");
}
#endif

/*
 * The installed app is an ordinary application: it may only mount its own
 * extdata, so it cannot touch the eShop's archive.  The Homebrew Launcher
 * runs with enough privilege, which is why the bundled .3dsx can do it.
 * Explain that here rather than offering an action that always fails.
 */
#ifdef MUSIC_CHANGER_CIA
static void explain_launcher(void)
{
	draw_header("Theme install needs the Homebrew Launcher");
	printf("  The eShop keeps its music in its own extdata\n");
	printf("  archive.  An installed app is not allowed to\n");
	printf("  open another title's archive - only the\n");
	printf("  Homebrew Launcher is.\n\n");
	printf("  1. Choose 'Install .3dsx' above.\n");
	printf("  2. Open the Homebrew Launcher.\n");
	printf("  3. Run 'eShop Music Changer' from there.\n\n");
	printf("  That build installs and restores the themes.\n");
	printf("\n   Press B to go back.\n");
}
#endif /* MUSIC_CHANGER_CIA -- explain_launcher */

#ifndef MUSIC_CHANGER_CIA
static int pick_theme(void)
{
	int cursor = 0;
	for (;;) {
		draw_header("Choose a theme  (B to go back)");
		for (int i = 0; i < theme_count; i++) {
			const char *label = theme_names[i];
			printf("   \x1b[%s%-28s\x1b[0m\n",
			       cursor == i ? "7;37m> " : "0;37m  ", label);
		}
		printf("\n\n   \x1b[0;37mUp/Down to move   A to install\x1b[0m\n");

		hidScanInput();
		u32 kDown = hidKeysDown();
		if (kDown & KEY_DOWN)  cursor = (cursor + 1) % theme_count;
		if (kDown & KEY_UP)    cursor = (cursor + theme_count - 1) % theme_count;
		if (kDown & KEY_B)     return -1;
		if (kDown & KEY_A)     return cursor;
		if (kDown & KEY_START) return -1;

		gspWaitForVBlank();
	}
}
#endif

static void wait_for_b(void)
{
	for (;;) {
		hidScanInput();
		if (hidKeysDown() & (KEY_B | KEY_A | KEY_START)) return;
		gspWaitForVBlank();
	}
}

/* ------------------------------------------------------------------ */
/* Main                                                                */
/* ------------------------------------------------------------------ */

int main(int argc, char **argv)
{
	APT_SetAppCpuTimeLimit(30);
	gfxInitDefault();
	consoleInit(GFX_TOP, NULL);

	/* An installed CIA does not auto-mount its RomFS; a .3dsx does. */
	romfsInit();

#ifndef MUSIC_CHANGER_CIA
	scan_themes();
#endif

	int cursor = 0;
	for (;;) {
		draw_menu(cursor);

		hidScanInput();
		u32 kDown = hidKeysDown();
		if (kDown & KEY_DOWN)  cursor = (cursor + 1) % 3;
		if (kDown & KEY_UP)    cursor = (cursor + 2) % 3;
		if (kDown & KEY_B && cursor == 2) break;
		if (kDown & KEY_START) break;

		if (kDown & KEY_A) {
			if (cursor == 2) { break; }

#ifdef MUSIC_CHANGER_CIA
			if (cursor == 0) {
				draw_header("Installing the .3dsx...");
				printf("\n");
				install_3dsx();
				printf("\n   Press B to go back.\n");
				wait_for_b();
			} else {
				explain_launcher();
				wait_for_b();
			}
#else
			if (cursor == 0) {
				if (theme_count == 0) {
					draw_header("No themes found");
					printf("   This build has no themes.\n");
					printf("\n   Press B to go back.\n");
					wait_for_b();
				} else {
					int pick = pick_theme();
					if (pick >= 0) {
						draw_header("Installing...");
						printf("   Theme: %s\n\n", theme_names[pick]);
						install_theme(theme_names[pick]);
						printf("\n   Press B to go back.\n");
						wait_for_b();
					}
				}
			} else {
				draw_header("Restoring the original theme...");
				printf("\n");
				restore_theme();
				printf("\n   Press B to go back.\n");
				wait_for_b();
			}
#endif
		}

		gspWaitForVBlank();
	}

	romfsExit();
	gfxExit();
	return 0;
}
