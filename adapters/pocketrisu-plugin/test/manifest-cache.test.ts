// Incremental manifest (Track A, A2): identical output to buildManifest, hashing only what changed.
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { bodyKey, buildManifest, createManifestBuilder } from '../src/manifest';
import type { HostChat, HostMessage } from '../src/types';
import { samples } from './samples';

const VECTORS = new URL('../../../fixtures/unit/revision-hash-v1.json', import.meta.url);

function makeChat(id: string, n: number): HostChat {
  const message: HostMessage[] = [];
  for (let i = 0; i < n; i++) {
    message.push(i % 2 === 0
      ? { role: 'user', data: `user ${i}`, chatId: `u${i}` }
      : { role: 'char', data: `reply ${i}`, chatId: `c${i}`, saying: 'bot', generationInfo: { generationId: `c${i}` } });
  }
  return { id, name: 'chat', message };
}

type Build = ReturnType<typeof createManifestBuilder>;

/** Build with the cache from a fresh snapshot (the host returns copies), and compare with no cache. */
async function check(build: Build, chat: HostChat) {
  const snapshot = structuredClone(chat);
  const cached = await build(snapshot, 'bot', { characterName: 'Bot' });
  const plain = await buildManifest(structuredClone(chat), 'bot', { characterName: 'Bot' });
  expect(cached.request).toEqual(plain.request);
  for (const m of plain.request.messages) {
    const key = bodyKey(m.host_logical_id, m.revision_hash);
    expect(cached.bodies.get(key)).toEqual(plain.bodies.get(key));
  }
  return cached;
}

describe('createManifestBuilder', () => {
  it('hashes nothing for an unchanged chat and only new or changed messages otherwise', async () => {
    const build = createManifestBuilder();
    const chat = makeChat('a', 10_000);
    expect((await check(build, chat)).hashed).toBe(10_000);
    expect((await check(build, chat)).hashed).toBe(0);

    chat.message.push({ role: 'user', data: 'new', chatId: 'new-u' },
      { role: 'char', data: 'new reply', chatId: 'new-c', generationInfo: { generationId: 'new-c' } });
    expect((await check(build, chat)).hashed).toBe(2);

    const before = (await check(build, chat)).request.messages;
    chat.message[42]!.data = 'deep edit';
    const after = await check(build, chat);
    expect(after.hashed).toBe(1);
    expect(after.request.messages[42]!.revision_hash).not.toBe(before[42]!.revision_hash);
  });

  it('sees every hash and entry input change', async () => {
    const build = createManifestBuilder();
    const chat = makeChat('b', 12);
    await check(build, chat);
    const m = chat.message as HostMessage[];
    const changes: [string, () => void][] = [
      ['disable', () => { m[1]!.disabled = true; }],
      ['cut', () => { m[2]!.disabled = 'allBefore'; }],
      ['enable', () => { delete m[1]!.disabled; }],
      ['swipe', () => { m[3] = { ...m[3]!, swipes: ['a', 'b'], swipeId: 1, data: 'b' }; }],
      ['swipe back', () => { m[3]!.swipeId = 0; m[3]!.data = 'a'; }],
      ['swipe added, selection kept', () => { m[3]!.swipes!.push('c'); }],
      ['continue', () => { m[5]!.data += ' more'; m[5]!.generationInfo = { generationId: 'g-new' }; }],
      ['generation id only', () => { m[5]!.generationInfo = { generationId: 'g-only' }; }],
      ['swipe id only (same text)', () => { m[10] = { ...m[10]!, swipes: ['same', 'same'], swipeId: 0, data: 'same' }; }],
      ['swipe id 0 → 1', () => { m[10]!.swipeId = 1; }],
      ['reroll', () => { m[11] = { role: 'char', data: 'rerolled', chatId: 'r11', generationInfo: { generationId: 'r11' } }; }],
      ['role', () => { m[4]!.role = 'char'; }],
      ['saying', () => { m[7]!.saying = 'other'; }],
      ['name', () => { m[6]!.name = 'Hinata'; }],
      ['otherUser', () => { m[6]!.otherUser = true; }],
      ['comment', () => { m[8]!.isComment = true; }],
      ['special comment in data only', () => { m[9] = { ...m[9]!, swipes: ['x'], swipeId: 0, data: '{{specialcomment::a::}}' }; }],
      ['data only (selected swipe unchanged)', () => { m[9]!.data = '{{specialcomment::b::}}'; }],
      ['no chatId', () => { m.push({ role: 'user', data: 'anonymous' }); }],
      ['duplicate id', () => { m.push({ ...m[0]!, data: 'same id, other text' }); }],
      ['object in a field', () => { (m[0] as unknown as Record<string, unknown>).name = { odd: true }; }],
    ];
    for (const [label, change] of changes) {
      change();
      const out = await check(build, chat);
      expect(out.hashed, label).toBeGreaterThan(0);
    }
    // Order and membership come from the host array on every call; only the three messages that are
    // never cached (no id, repeated id, object field) are hashed again.
    m.splice(2, 0, m.splice(6, 1)[0]!);
    expect((await check(build, chat)).hashed).toBe(3);
    m.splice(3, 1);
    expect((await check(build, chat)).hashed).toBe(3);
  });

  it('keeps chats apart and survives eviction', async () => {
    const build = createManifestBuilder();
    const a = makeChat('a', 6);
    const imported = structuredClone(a); // import keeps message ids under a new chat id (H6)
    imported.id = 'imported';
    imported.message[1]!.data = 'changed in the copy';
    await check(build, a);
    expect((await check(build, imported)).hashed).toBe(6);
    expect((await check(build, a)).hashed).toBe(0);
    await check(build, makeChat('c', 3));
    await check(build, makeChat('d', 3)); // evicts 'a' and 'imported'
    expect((await check(build, a)).hashed).toBe(6);
  });

  it('matches the committed cross-language vectors', async () => {
    const vectors = JSON.parse(readFileSync(VECTORS, 'utf8')) as { revision_hash: string }[];
    const build = createManifestBuilder();
    for (let run = 0; run < 2; run++) { // cold, then fully cached
      const out = await build({ id: 'v', message: structuredClone(samples) }, null);
      expect(out.request.messages.map((m) => m.revision_hash)).toEqual(vectors.map((v) => v.revision_hash));
      expect(out.hashed).toBe(run === 0 ? samples.length : 0);
    }
  });
});
