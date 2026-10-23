import { Router } from 'express';

// GET /p01/policylist/3/:cc
// BOSS task policy list (XML) requested before the shop boots.
export const policylist = Router();

policylist.get('/p01/policylist/3/:cc', (req, res) => {
	// TODO(phase3): replace with Nintendo's captured original — schema unknown
	const xml = [
		'<?xml version="1.0" encoding="UTF-8"?>',
		`<policylist version="1" country="${req.params.cc}">`,
		'</policylist>',
		'',
	].join('\n');

	res.type('application/xml').send(xml);
});
