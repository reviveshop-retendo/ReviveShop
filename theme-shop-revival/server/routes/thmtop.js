import { Router } from 'express';
import { buildBoss } from '../boss/index.js';
import { loadCatalog } from '../config.js';

// GET /p01/nsa/:shopId/thmtop/:cc/:lang/top
// The shop landing page (categories/entries + top banner).
export const thmtop = Router();

thmtop.get('/p01/nsa/:shopId/thmtop/:cc/:lang/top', (req, res) => {
	const catalog = loadCatalog();
	const { cc, lang } = req.params;

	// TODO(phase3): replace JSON with Nintendo's real binary layout once captured
	const content = Buffer.from(
		JSON.stringify(
			{
				type: 'thmtop',
				region: { cc, lang },
				entries: catalog.categories.map((c) => ({ listId: c.listId })),
			},
			null,
			0
		)
	);

	res.type('application/octet-stream').send(buildBoss(content));
});
