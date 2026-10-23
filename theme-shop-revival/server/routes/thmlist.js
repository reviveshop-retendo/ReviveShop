import { Router } from 'express';
import { buildBoss } from '../boss/index.js';
import { loadCatalog } from '../config.js';

// GET /p01/nsa/:shopId/thmlist/:cc/:lang/:listId
// A category page (title, developer, member themes).
export const thmlist = Router();

thmlist.get('/p01/nsa/:shopId/thmlist/:cc/:lang/:listId', (req, res) => {
	const catalog = loadCatalog();
	const { cc, lang, listId } = req.params;
	const category = catalog.categories.find((c) => c.listId === listId);

	// TODO(phase3): replace JSON with Nintendo's real binary layout once captured
	// (known anchors: title @0x2D4 UTF-16, developer @0x394 UTF-16)
	const content = Buffer.from(
		JSON.stringify({
			type: 'thmlist',
			region: { cc, lang },
			listId,
			title: category ? `Category ${listId}` : 'Unknown Category',
			themes: category?.themes ?? [],
		})
	);

	res.type('application/octet-stream').send(buildBoss(content, { ns_data_id: Number(listId) || 1 }));
});
