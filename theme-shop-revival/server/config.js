import { readFileSync, existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
export const ROOT = root;

// Load data/.env (manual, no dotenv dependency)
const envPath = join(root, 'data', '.env');
if (existsSync(envPath)) {
	for (const line of readFileSync(envPath, 'utf8').split('\n')) {
		const m = line.match(/^([A-Z0-9_]+)=(.*)$/);
		if (m && !(m[1] in process.env)) process.env[m[1]] = m[2].trim();
	}
}

export const SHOP_ID = 'dMtiFHzm5OOf0y2O'; // shop identifier used by the 3DS in all Theme Shop URLs
export const BOSS_AES_KEY = process.env.BOSS_AES_KEY ?? null;
export const PORT = Number(process.env.PORT ?? 443);
export const LAN_IP = process.env.LAN_IP ?? null;

export function loadCatalog() {
	return JSON.parse(readFileSync(join(root, 'server', 'catalog', 'themes.json'), 'utf8'));
}
