// Cross-language revision-hash vectors. The same file is checked by the sidecar's pytest suite.
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { canonicalJson } from '../src/canonical';
import { sha256Hex } from '../src/hash';
import { hashPayload, revisionMetadata, selectedContent } from '../src/manifest';
import { samples } from './samples';

const VECTORS = new URL('../../../fixtures/unit/revision-hash-v1.json', import.meta.url);

async function compute() {
  return Promise.all(
    samples.map(async (m) => ({
      metadata: revisionMetadata(m),
      content: selectedContent(m),
      canonical: canonicalJson(hashPayload(m)),
      revision_hash: await sha256Hex(canonicalJson(hashPayload(m))),
    })),
  );
}

describe('revision hash v1 vectors', () => {
  it('match the committed cross-language vectors', async () => {
    const vectors = await compute();
    if (process.env.UPDATE_VECTORS || !existsSync(VECTORS)) {
      writeFileSync(VECTORS, JSON.stringify(vectors, null, 2) + '\n');
    }
    expect(JSON.parse(readFileSync(VECTORS, 'utf8'))).toEqual(vectors);
  });

  it('selects the active swipe and keeps trailing whitespace', async () => {
    const [, crlf, , , swipe] = await compute();
    expect(crlf!.canonical).toContain('"selectedContent":"windows\\nline\\nendings  "');
    expect(swipe!.canonical).toContain('"selectedContent":"A"');
  });
});
