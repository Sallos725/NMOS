// Cross-language revision-hash vectors. The same file is checked by the sidecar's pytest suite.
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { canonicalJson } from '../src/canonical';
import { sha256Hex } from '../src/hash';
import { hashPayload, revisionMetadata, selectedContent } from '../src/manifest';
import type { HostMessage } from '../src/types';

const VECTORS = new URL('../../../fixtures/unit/revision-hash-v1.json', import.meta.url);

const samples: HostMessage[] = [
  { role: 'user', data: 'plain ascii', chatId: 'u1' },
  { role: 'user', data: 'windows\r\nline\r\nendings  ', chatId: 'u2' },
  { role: 'char', data: '한국어 메시지와 이모지 🎐', chatId: 'c1', generationInfo: { generationId: 'c1' }, saying: 'char-1' },
  { role: 'char', data: 'Café NFD → NFC', chatId: 'c2', name: 'Hinata', disabled: true },
  { role: 'char', data: 'B', swipes: ['A', 'B'], swipeId: 0, chatId: 'c3', generationInfo: { generationId: 'g3' } },
  { role: 'user', data: 'quote " backslash \\ tab\t ctrl del', chatId: 'u3', disabled: 'allBefore', otherUser: false },
  { role: 'char', data: '{{specialcomment::branchedfrom::o::Name::m::}}', chatId: 'c4', isComment: true, disabled: true },
  { role: 'user', data: 'lone surrogate \ud800 here', chatId: 'u4' },
];

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
