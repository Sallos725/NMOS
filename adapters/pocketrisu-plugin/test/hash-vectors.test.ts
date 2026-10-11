// Cross-language revision-hash vectors. The same file is checked by the sidecar's pytest suite.
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { canonicalJson } from '../src/canonical';
import { sha256Hex } from '../src/hash';
import { hashPayload, revisionMetadata, rewritten, selectedContent } from '../src/manifest';
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

  it('hashes the text the host sends (data, not the generated swipe) and keeps trailing whitespace', async () => {
    const [, crlf, , , swipe] = await compute();
    expect(crlf!.canonical).toContain('"selectedContent":"windows\\nline\\nendings  "');
    // A trigger or Lua rewrote `data` after the reply was generated: memory follows what the model is sent.
    expect(swipe!.canonical).toContain('"selectedContent":"B"');
  });

  it('falls back to the selected swipe only without data, and tells a rewritten reply apart', () => {
    expect(selectedContent({ role: 'char', swipes: ['a', 'b'], swipeId: 1 } as never)).toBe('b');
    expect(rewritten({ role: 'char', data: 'b', swipes: ['a', 'b'], swipeId: 1 } as never)).toBe(false);
    expect(rewritten({ role: 'char', data: 'B', swipes: ['a', 'b'], swipeId: 1 } as never)).toBe(true);
    expect(rewritten({ role: 'char', data: 'B' } as never)).toBe(false);
  });
});
