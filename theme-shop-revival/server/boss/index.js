import { encrypt3DS, decrypt3DS } from '@pretendonetwork/boss-crypto';
import { BOSS_AES_KEY } from '../config.js';

// Builds an encrypted 3DS BOSS container around `content`.
// program_id / content_datatype / ns_data_id defaults are placeholders:
// real values get sniffed from Nintendo's live files during reference capture.
export function buildBoss(content, overrides = {}) {
	if (!BOSS_AES_KEY) throw new Error('BOSS_AES_KEY missing — run `npm run extract-key` first');

	const opts = {
		program_id: overrides.program_id ?? 0x0004003000008f02n,
		content_datatype: overrides.content_datatype ?? 65537,
		ns_data_id: overrides.ns_data_id ?? 1,
		version: overrides.version ?? 1,
		content: Buffer.isBuffer(content) ? content : Buffer.from(content),
	};

	const serial = overrides.serial_number ?? BigInt(Date.now());
	return encrypt3DS(BOSS_AES_KEY, serial, [opts]);
}

export function openBoss(buffer) {
	if (!BOSS_AES_KEY) throw new Error('BOSS_AES_KEY missing — run `npm run extract-key` first');
	return decrypt3DS(buffer, BOSS_AES_KEY);
}
