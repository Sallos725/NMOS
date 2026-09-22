// Bundle src/entry.ts into one PocketRisu V3 plugin file with its metadata header.
import { build } from 'esbuild';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';

const pkg = JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf8'));
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
  '//@arg reserved_memory_tokens int Max packet tokens; lower the host max context by this much (0 = 600)',
  '//@arg deadline_ms int Hard request-path deadline in ms (0 = 800)',
  '//@arg inject_position string before_last_user (default) or end',
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
  define: { __NMOS_VERSION__: JSON.stringify(pkg.version) },
});

mkdirSync(new URL('../dist/', import.meta.url), { recursive: true });
const out = new URL('../dist/nmos-pocketrisu.js', import.meta.url);
writeFileSync(out, header + result.outputFiles[0].text);
console.log(`wrote ${out.pathname}`);
