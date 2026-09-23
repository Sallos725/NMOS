import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const pkg = JSON.parse(
  readFileSync(new URL('../package.json', import.meta.url), 'utf8'),
) as { version: string };
const buildScript = readFileSync(new URL('../scripts/build.mjs', import.meta.url), 'utf8');
const dist = readFileSync(new URL('../dist/nmos-pocketrisu.js', import.meta.url), 'utf8');

const UPDATE_URL =
  'https://raw.githubusercontent.com/Sallos725/NMOS/main/adapters/pocketrisu-plugin/dist/nmos-pocketrisu.js';

describe('PocketRisu plugin update metadata', () => {
  it('keeps version and native update URL in the build template and tracked bundle', () => {
    expect(buildScript).toContain('`//@version ${pkg.version}`');
    expect(buildScript).toContain(`//@update-url ${UPDATE_URL}`);

    const header = dist.split('\n').slice(0, 16).join('\n');
    expect(header).toContain(`//@version ${pkg.version}`);
    expect(header).toContain(`//@update-url ${UPDATE_URL}`);
  });
});
