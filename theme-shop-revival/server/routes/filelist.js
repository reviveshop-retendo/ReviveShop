import { Router } from 'express';
import { loadCatalog } from '../config.js';

// GET /p01/filelist/:shopId/thmdtls?c={cc}&l={lang}&a3={index}
// Plain-text TSV listing of theme details. Per 3dbrew: 2 unknown header
// lines, then one row per theme:
//   col1 theme list id | col2 price (empty if free) | col3 same as col1
//   col4 ? | col5 themes list index count | col6 ? | col7 added timestamp
export const filelist = Router();

filelist.get('/p01/filelist/:shopId/thmdtls', (req, res) => {
	const catalog = loadCatalog();
	const { c = '??', l = 'en', a3 = '1' } = req.query;

	const rows = [];
	let index = 0;
	for (const [themeId, theme] of Object.entries(catalog.themes)) {
		index += 1;
		rows.push(
			[
				themeId,
				theme.price ?? '',
				themeId,
				'', // TODO(phase3): learn from Nintendo's live response
				index,
				'',
				theme.added,
			].join('\t')
		);
	}

	// TODO(phase3): first two lines are unknown — replace with captured originals
	const body = [`theme-shop-revival c=${c} l=${l} a3=${a3}`, `${rows.length}`, ...rows, ''].join('\n');

	res.type('text/plain').send(body);
});
