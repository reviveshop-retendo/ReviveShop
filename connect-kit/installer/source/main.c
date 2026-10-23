#include <3ds.h>
#include <stdio.h>
#include <string.h>
#include <dirent.h>
#include <sys/stat.h>

#define ROMFS_PATCH_DIR "romfs:/patches"
#define SD_LUMA_DIR     "sdmc:/luma"
#define SD_MOD_DIR      "sdmc:/luma/sysmodules"

static int copy_file(const char *src, const char *dst) {
	FILE *in = fopen(src, "rb");
	if (!in) return -1;
	FILE *out = fopen(dst, "wb");
	if (!out) { fclose(in); return -2; }

	char buf[16384];
	size_t n;
	int rc = 0;
	while ((n = fread(buf, 1, sizeof buf, in)) > 0) {
		if (fwrite(buf, 1, n, out) != n) { rc = -3; break; }
	}
	fclose(in);
	fclose(out);
	return rc;
}

static void ensure_dirs(void) {
	mkdir(SD_LUMA_DIR, 0777);
	mkdir(SD_MOD_DIR, 0777);
}

static void install_patches(void) {
	DIR *d = opendir(ROMFS_PATCH_DIR);
	if (!d) { printf("  cannot open %s\n", ROMFS_PATCH_DIR); return; }

	int ok = 0, fail = 0;
	struct dirent *e;
	while ((e = readdir(d))) {
		if (e->d_name[0] == '.') continue;
		char src[512], dst[512];
		snprintf(src, sizeof src, "%s/%s", ROMFS_PATCH_DIR, e->d_name);
		snprintf(dst, sizeof dst, "%s/%s", SD_MOD_DIR, e->d_name);
		if (copy_file(src, dst) == 0) { printf("  installed %s\n", e->d_name); ok++; }
		else { printf("  FAILED    %s\n", e->d_name); fail++; }
	}
	closedir(d);
	printf("\n  %d installed, %d failed.\n", ok, fail);
}

static void uninstall_patches(void) {
	DIR *d = opendir(ROMFS_PATCH_DIR);
	if (!d) return;
	struct dirent *e;
	while ((e = readdir(d))) {
		if (e->d_name[0] == '.') continue;
		char dst[512];
		snprintf(dst, sizeof dst, "%s/%s", SD_MOD_DIR, e->d_name);
		if (remove(dst) == 0) printf("  removed   %s\n", e->d_name);
	}
	closedir(d);
}

int main(int argc, char **argv) {
	gfxInitDefault();
	fsInit();
	romfsInit();
	consoleInit(GFX_TOP, NULL);

	printf("\x1b[2;0HReviveShop Installer\n");
	printf("===================\n\n");
	printf("Target: %s\n\n", SD_MOD_DIR);
	printf("Press A: Install ReviveShop patches\n");
	printf("Press X: Remove ReviveShop patches\n");
	printf("Press B: Exit\n");

	while (aptMainLoop()) {
		hidScanInput();
		u32 k = hidKeysDown();

		if (k & KEY_B) break;

		if (k & KEY_A) {
			ensure_dirs();
			printf("\n\x1b[2;22HInstalling...      \n");
			install_patches();
			printf("\n  Reboot the console to apply.\n");
		}

		if (k & KEY_X) {
			printf("\n\x1b[2;22HRemoving...        \n");
			uninstall_patches();
			printf("\n  Reboot the console to apply.\n");
		}

		gspWaitForVBlank();
	}

	romfsExit();
	fsExit();
	gfxExit();
	return 0;
}
