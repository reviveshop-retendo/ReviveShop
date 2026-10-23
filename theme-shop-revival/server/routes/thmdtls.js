import { Router } from 'express';
import { buildBoss } from '../boss/index.js';
import { loadCatalog } from '../config.js';

// GET /p01/nsa/:shopId/thmdtls/:cc/:lang/:themeId
// Theme detail page (task policy + purchase info for one theme).
export const thmdtls = Router();

thmdtls.get('/p01/nsa/:shopId/thmdtls/:cc/:lang/:themeId', (req, res) => {
	const catalog = loadCatalog();
	const { cc, lang, themeId } = req.params;
	const theme = catalog.themes[themeId];

	// TODO(phase3): real response = BOSS task policy XML (+ price/metadata);
	// known: details are per-theme, price column empty for free themes
	const content = Buffer.from(
		JSON.stringify({
			type: 'thmdtls',
			region: { cc, lang },
			themeId,
			found: Boolean(theme),
			name: theme?.name ?? null,
			price: theme?.price ?? null,
		})
	);

	const bossOpts = theme?.boss
		? {
				program_id: BigInt(theme.boss.programId),
				content_datatype: theme.boss.contentDatatype,
				ns_data_id: theme.boss.nsDataId,
		  }
		: {};

	res.type('application/octet-stream').send(buildBoss(content, bossOpts));
});
