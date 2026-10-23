#!/usr/bin/env node
// Generates self-signed certs: one per Theme Shop hostname (CN+SAN match for
// SNI clients) plus a multi-SAN default (server.key/crt) for no-SNI/local use.
// Usage: node tools/gen-certs.js [lan-ip] [--force]
import { execFileSync } from 'node:child_process';
import { mkdirSync, existsSync, writeFileSync, rmSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import os from 'node:os';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const certDir = join(root, 'data', 'certs');

const args = process.argv.slice(2);
const force = args.includes('--force');
const ipArg = args.find((a) => !a.startsWith('--'));

if (force) rmSync(certDir, { recursive: true, force: true });
mkdirSync(certDir, { recursive: true });

const SHOP_HOSTS = [
	'npdl.cdn.nintendowifi.net',
	'npfl.c.app.nintendowifi.net',
	'nppl.c.app.nintendowifi.net',
];

function lanIp() {
	if (ipArg) return ipArg;
	const ifaces = os.networkInterfaces();
	for (const list of Object.values(ifaces)) {
		for (const i of list ?? []) {
			if (i.family === 'IPv4' && !i.internal) return i.address;
		}
	}
	return '127.0.0.1';
}

const ip = lanIp();

function genCert(name, cn, sanEntries) {
	const keyPath = join(certDir, `${name}.key`);
	const certPath = join(certDir, `${name}.crt`);
	if (existsSync(certPath) && existsSync(keyPath)) return false;

	const extFile = join(certDir, `${name}.cnf`);
	writeFileSync(
		extFile,
		`[req]
distinguished_name = dn
req_extensions = ext
prompt = no

[dn]
CN = ${cn}

[ext]
subjectAltName = ${sanEntries.join(',')}
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
basicConstraints = CA:FALSE
`
	);

	execFileSync(
		'openssl',
		[
			'req', '-x509', '-newkey', 'rsa:2048', '-sha256',
			'-days', '3650',
			'-nodes',
			'-keyout', keyPath,
			'-out', certPath,
			'-config', extFile,
		],
		{ stdio: ['ignore', 'ignore', 'inherit'] }
	);
	rmSync(extFile);
	console.log(`Generated ${name}.crt (CN=${cn})`);
	return true;
}

// Per-host certs for SNI — CN matches each hostname exactly.
for (const host of SHOP_HOSTS) {
	genCert(host, host, [`DNS:${host}`, `IP:${ip}`, 'IP:127.0.0.1']);
}

// Default/no-SNI cert — one CN, all hosts in SANs.
genCert('server', SHOP_HOSTS[0], [
	...SHOP_HOSTS.map((h) => `DNS:${h}`),
	'localhost',
	`IP:${ip}`,
	'IP:127.0.0.1',
]);

console.log(`Done in ${certDir} for LAN IP ${ip}`);
