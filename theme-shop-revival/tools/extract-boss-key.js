#!/usr/bin/env node
// Extracts the BOSS AES key (AES keyslot 0x38 normalkey) from a boot9 dump.
// The BOSS key is common to all consoles (not console-unique), so any valid boot9 dump works.
// Offset math (see AntiMach/allbadge-tool + 3dbrew AES_Registers):
//   0x8000 (skip first bootrom half) + 0x5860 (keyarea) + 0x170 (skip AESIV) + 0x200 = 0xDBD0
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const boot9Path = process.argv[2] ?? join(process.env.HOME, '3ds', 'boot9.bin');
const outPath = join(root, 'data', '.env');
const KEY_OFFSET = 0xdbd0;
const KEY_SIZE = 0x10;

const boot9 = readFileSync(boot9Path);
if (boot9.length !== 0x10000) {
	console.error(`Unexpected boot9 size: 0x${boot9.length.toString(16)} (expected 0x10000)`);
	process.exit(1);
}

const key = boot9.subarray(KEY_OFFSET, KEY_OFFSET + KEY_SIZE);
if (key.every((b) => b === 0) || key.every((b) => b === 0xff)) {
	console.error('Extracted key looks invalid (all 0x00/0xFF) — is this a real boot9 dump?');
	process.exit(1);
}

const hex = key.toString('hex').toUpperCase();
const envLine = `BOSS_AES_KEY=${hex}`;

let env = existsSync(outPath) ? readFileSync(outPath, 'utf8') : '';
if (/^BOSS_AES_KEY=/m.test(env)) {
	env = env.replace(/^BOSS_AES_KEY=.*$/m, envLine);
} else {
	env = env.trimEnd() + (env.trim() ? '\n' : '') + envLine + '\n';
}
writeFileSync(outPath, env);

console.log(`BOSS AES key extracted from ${boot9Path}`);
console.log(`  offset 0x${KEY_OFFSET.toString(16)}: ${hex}`);
console.log(`  written to ${outPath}`);
