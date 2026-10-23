import { readFileSync, appendFileSync, existsSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';
import https from 'node:https';
import tls from 'node:tls';
import express from 'express';
import { createRequire } from 'module';

const require = createRequire(import.meta.url);
const constants = require('constants');

import { ROOT, PORT, SHOP_ID } from './config.js';
import { thmtop } from './routes/thmtop.js';
import { thmlist } from './routes/thmlist.js';
import { thmdtls } from './routes/thmdtls.js';
import { filelist } from './routes/filelist.js';
import { policylist } from './routes/policylist.js';

const SHOP_HOSTS = ['npdl.cdn.nintendowifi.net','npfl.c.app.nintendowifi.net','nppl.c.app.nintendowifi.net'];
const certDir = join(ROOT, 'data', 'certs');
const keyPath = join(certDir, 'server.key');
const certPath = join(certDir, 'server.crt');
if (!existsSync(keyPath) || !existsSync(certPath)) { console.error('Missing TLS certs'); process.exit(1); }

const logDir = join(ROOT, 'data', 'logs');
mkdirSync(logDir, { recursive: true });
const logPath = join(logDir, 'requests.jsonl');

const app = express();
app.use((req,res,next)=>{ const chunks=[]; req.on('data',c=>chunks.push(c)); req.on('end',()=>{ const raw=Buffer.concat(chunks); const entry={ts:new Date().toISOString(),method:req.method,url:req.originalUrl,http:req.httpVersion,headers:req.headers,bodyLen:raw.length,body:raw.length?raw.toString('base64'):null}; appendFileSync(logPath, JSON.stringify(entry)+'\n'); console.log(entry.ts, entry.method, entry.url); next(); }); });
app.use('/',thmtop); app.use('/',thmlist); app.use('/',thmdtls); app.use('/',filelist); app.use('/',policylist);
app.use((req,res)=>res.status(404).type('text/plain').send('not found'));

const defaultKey = readFileSync(keyPath);
const defaultCert = readFileSync(certPath);
const baseOpts = { key: defaultKey, cert: defaultCert, secureOptions: constants.SSL_OP_NO_SSLv2 | constants.SSL_OP_NO_SSLv3 | constants.SSL_OP_NO_TLSv1_2 | constants.SSL_OP_NO_TLSv1_3, ciphers: 'RC4-MD5:RC4-SHA:DES-CBC3-SHA:AES128-SHA:AES256-SHA:ALL:@SECLEVEL=0', honorCipherOrder: true };

const server = https.createServer({ ...baseOpts, SNICallback(servername, cb){ try { const hk=join(certDir,servername+'.key'), hc=join(certDir,servername+'.crt'); if(SHOP_HOSTS.includes(servername)&&existsSync(hk)&&existsSync(hc)){ cb(null,tls.createSecureContext({key:readFileSync(hk),cert:readFileSync(hc),...baseOpts})); } else { cb(null,tls.createSecureContext(baseOpts)); } } catch(e){ cb(e); } } }, app);
server.listen(PORT, ()=>{ console.log(`Theme Shop Revival listening on https://0.0.0.0:${PORT}`); console.log(`shop id: ${SHOP_ID}`); });
