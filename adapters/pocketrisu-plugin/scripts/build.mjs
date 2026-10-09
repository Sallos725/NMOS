// Bundle src/entry.ts into one PocketRisu V3 plugin file with its metadata header.
import { build } from 'esbuild';
import { createHash } from 'node:crypto';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';

const pkg = JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf8'));
const PLACEHOLDER = 'nmos-build:000000000000';
const header = [
  '//@name nmos_memory',
  '//@display-name NMOS Narrative Memory',
  '//@api 3.0',
  `//@version ${pkg.version}`,
  '//@link https://github.com/Sallos725/NMOS Documentation',
  '//@update-url https://raw.githubusercontent.com/Sallos725/NMOS/main/adapters/pocketrisu-plugin/dist/nmos-pocketrisu.js',
  '//@arg sidecar_url string NMOS sidecar URL (empty = http://127.0.0.1:8790)',
  '//@arg auth_token string Optional; only if the sidecar sets NMOS_AUTH_TOKEN',
  '//@arg disabled int 1 = pass every request through untouched',
  '//@arg reserved_memory_tokens int Max packet tokens; lower the host max context by this much (0 = 4000)',
  '//@arg deadline_ms int Hard request-path deadline in ms (0 = 3000)',
  '//@arg inject_position string before_last_user (default) or end',
  '//@arg route string auto (default) / direct / server — how to reach the sidecar',
  '//@arg language string Panel language: ko (default) or en',
  '//@arg hud int 1 = progress display on the chat screen (turn it on from the NMOS panel)',
  '//@arg disabled_chats string Chat ids NMOS is off for (switched from the NMOS panel or the chat menu)',
  '',
].join('\n');

const result = await build({
  entryPoints: [new URL('../src/entry.ts', import.meta.url).pathname],
  bundle: true,
  format: 'iife',
  platform: 'browser',
  target: 'es2022',
  write: false,
  legalComments: 'none',
  define: { __NMOS_VERSION__: JSON.stringify(pkg.version), __NMOS_BUILD__: JSON.stringify(PLACEHOLDER) },
});

// The build id (ADR 0037) is a hash of the file with a placeholder in its place: the same source gives the
// same id, and the sidecar reads it back from the file it ships ("nmos-build:<12 hex>").
const draft = header + result.outputFiles[0].text;
if (!draft.includes(PLACEHOLDER)) throw new Error('build id placeholder missing from the bundle');
const id = createHash('sha256').update(draft).digest('hex').slice(0, 12);
mkdirSync(new URL('../dist/', import.meta.url), { recursive: true });
const out = new URL('../dist/nmos-pocketrisu.js', import.meta.url);
writeFileSync(out, draft.replaceAll(PLACEHOLDER, `nmos-build:${id}`));
console.log(`wrote ${out.pathname} (build ${id})`);
