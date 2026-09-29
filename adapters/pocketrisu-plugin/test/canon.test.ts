import { describe, expect, it, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { canonManifestId, canonTexts, heldKeys, loreKey, MAX_CANON_CHARS, type HostCard, type HostLoreEntry } from '../src/canon';
import { createAdapter, type HostPort, type HttpResult } from '../src/core';
import type { HostChat, PromptMessage } from '../src/types';

const kaito: HostLoreEntry = { id: 'lore-kaito', key: '카이토, 카이', comment: '카이토', content: '카이토는 견습 기사이고 하나의 소꿉친구다.',
  mode: 'normal', alwaysActive: false };
const world: HostLoreEntry = { id: 'lore-world', key: '', comment: '세계', content: '이 세계의 등대는 마법으로 빛난다.', mode: 'constant',
  alwaysActive: true };
const folder: HostLoreEntry = { id: 'lore-folder', comment: '장소', content: '', mode: 'folder' };
const tunnel: HostLoreEntry = { key: '비밀 통로', comment: '통로', content: '등대 지하에는 비밀 통로가 있다.', mode: 'normal' };
const market: HostLoreEntry = { id: 'lore-market', key: '시장, 어시장', content: '어시장은 새벽에만 열린다.', mode: 'normal' };
const card: HostCard = { name: '하나', desc: '하나는 항구 마을 등대지기의 딸이다.', personality: '밝고 고집이 세다.', scenario: '',
  firstMessage: '하나가 등대 문을 열었다.', alternateGreetings: ['하나가 부두에서 손을 흔들었다.'], globalLore: [kaito, world, folder] };
const chat: HostChat = { id: 'chat-1', note: '지금은 한겨울 밤이다.', localLore: [tunnel], fmIndex: -1, bindedPersona: 'p1',
  message: [{ role: 'user', data: '카이토는 어디 있어?', chatId: 'u0' }] };
const persona = { id: 'p1', name: '타쿠미', personaPrompt: '타쿠미는 항구 신문의 기자다.' };

describe('canon texts (ADR 0045)', () => {
  it('are the card story fields, the greeting in use, the note, the persona and every lorebook entry with content', () => {
    const texts = canonTexts(card, chat, [kaito, world, folder, tunnel, market], persona);
    expect(texts.map((t) => t.key)).toEqual(['card:name', 'card:desc', 'card:personality', 'card:greeting', 'note', 'persona',
      'lore:lore-kaito', 'lore:lore-world', loreKey(tunnel), 'lore:lore-market']);
    const byKey = Object.fromEntries(texts.map((t) => [t.key, t]));
    expect(byKey['card:greeting']!.text).toBe('하나가 등대 문을 열었다.');
    expect(byKey['lore:lore-kaito']!.metadata).toEqual({ scope: 'character', mode: 'normal', always_active: false,
      keys: ['카이토', '카이'], comment: '카이토' });
    expect(byKey[loreKey(tunnel)]!.metadata.scope).toBe('chat');
    expect(byKey['lore:lore-market']!.metadata.scope).toBe('module');
    expect(byKey.persona!.metadata).toEqual({ name: '타쿠미', persona_id: 'p1' });
    // the chat started from the first alternate greeting
    expect(canonTexts(card, { ...chat, fmIndex: 0 }, [], null).find((t) => t.key === 'card:greeting')!.text)
      .toBe('하나가 부두에서 손을 흔들었다.');
  });

  it('key an entry without an id by what names it, so an edit of its content keeps the key', () => {
    expect(loreKey(tunnel)).toMatch(/^lore:f[0-9a-f]{8}$/);
    expect(loreKey({ ...tunnel, content: '바뀐 내용' })).toBe(loreKey(tunnel));
    expect(loreKey({ ...tunnel, key: '다른 키' })).not.toBe(loreKey(tunnel));
    expect(loreKey({ ...tunnel, id: 'has spaces and 한글' })).toBe(loreKey(tunnel)); // not a key the sidecar takes
    const twins = canonTexts(null, chat, [tunnel, { ...tunnel, content: '두 번째' }], null).map((t) => t.key)
      .filter((k) => k.startsWith('lore:'));
    expect(twins).toEqual([loreKey(tunnel), `${loreKey(tunnel)}~1`]);
    // host ids x, x and x.1 stay three keys: `~` is never in an id the sidecar takes
    const ids = canonTexts(null, chat, [{ ...market }, { ...market, content: 'b' }, { ...market, id: 'lore-market.1', content: 'c' }], null)
      .map((t) => t.key).filter((k) => k.startsWith('lore:'));
    expect(new Set(ids).size).toBe(3);
    // a text past what the sidecar takes is not kept
    expect(canonTexts(null, { ...chat, note: 'x'.repeat(MAX_CANON_CHARS + 1) }, [], null).map((t) => t.key)).toEqual([]);
  });

  it('keep a text as the host has it, and hold it by its trimmed words (Copilot review of #154)', () => {
    const spaced = canonTexts(null, { ...chat, note: '  지금은 한겨울 밤이다.\n' }, [], null);
    expect(spaced[0]!.text).toBe('  지금은 한겨울 밤이다.\n');
    expect(heldKeys(spaced, [{ role: 'system', content: '지금은 한겨울 밤이다.' }])).toEqual(['note']);
    expect(canonTexts(null, { ...chat, note: '   ' }, [], null)).toEqual([]);
  });

  it('manifest ids are the sidecar\'s (fixtures/unit/canon-manifest-v1.json)', async () => {
    const doc = JSON.parse(readFileSync(new URL('../../../fixtures/unit/canon-manifest-v1.json', import.meta.url), 'utf8'));
    expect(await canonManifestId(doc.entries)).toBe(doc.id);
    expect(await canonManifestId([...doc.entries].reverse())).toBe(doc.id);
  });

  it('held by a prompt are the texts in it, as the host activated them (H19)', () => {
    const texts = canonTexts(card, chat, [kaito, world, tunnel, market], persona);
    const prompt: PromptMessage[] = [
      { role: 'system', content: `${card.desc}\n${card.personality}\n${world.content}\n${kaito.content}` },
      { role: 'system', content: `${chat.note}\n${persona.personaPrompt}` },
      { role: 'user', content: '카이토는 어디 있어? 하나' },
    ];
    expect(heldKeys(texts, prompt)).toEqual(['card:desc', 'card:personality', 'note', 'persona', 'lore:lore-kaito',
      'lore:lore-world']);
  });

  it('held by a prompt are texts with the host\'s names in, or nearly all of their lines (ADR 0047)', () => {
    const macro: HostCard = { ...card, desc: '{{char}}는 항구 마을 등대지기의 딸이다.\n{{char}}는 {{user}}를 오빠라고 부른다.' };
    const texts = canonTexts(macro, chat, [], persona);
    const sent = '하나는 항구 마을 등대지기의 딸이다.\n하나는 타쿠미를 오빠라고 부른다.';
    expect(heldKeys(texts, [{ role: 'system', content: sent }])).toEqual(['card:desc']);
    // a text whose other syntax the host rendered: its plain lines are there
    const long: HostCard = { ...card, desc: ['하나의 눈은 푸른색이고 머리는 은빛이다.', '하나는 매일 새벽 등대의 불을 확인한다.',
      '{{random::비::눈}}이 오는 날에는 문을 닫는다.', '하나는 바다를 무서워하지 않는다, 한 번도.', '하나는 편지를 모아 둔다, 상자 가득.',
      '하나의 어머니는 오래전에 바다로 떠났다.'].join('\n') };
    const rendered = long.desc!.replace('{{random::비::눈}}', '비').split('\n');
    const held = (lines: string[]) => heldKeys(canonTexts(long, chat, [], null), [{ role: 'system', content: lines.join('\n') }]);
    expect(held(rendered)).toEqual(['card:desc']);
    expect(held(rendered.slice(0, 3))).toEqual([]);  // most of it is missing: an edit since, or not sent
  });
});

describe('canon sync', () => {
  const prompt: PromptMessage[] = [
    { role: 'system', content: `${card.desc}\n${card.personality}\n${world.content}` },
    { role: 'user', content: '카이토는 어디 있어?' },
  ];
  const more = (tag: string): PromptMessage[] => structuredClone([...prompt, { role: 'user', content: tag }]);
  function host(handler: (path: string, body: any) => HttpResult | Promise<HttpResult>, opts: { delay?: number;
    lorebook?: () => Promise<HostLoreEntry[]>; conversation?: () => string } = {}) {
    const posts: { path: string; body: any }[] = [];
    const h: HostPort = {
      settings: async () => ({ sidecarUrl: 'http://s', authToken: '', enabled: true, reservedMemoryTokens: 600, deadlineMs: 500,
        injectPosition: 'before_last_user', route: 'direct', language: 'en' }),
      currentChat: async () => structuredClone(chat),
      card: vi.fn(async () => {
        if (opts.delay) await new Promise((r) => setTimeout(r, opts.delay));
        return card;
      }),
      lorebook: opts.lorebook ?? (async () => [kaito, world, folder, tunnel]),
      request: async (_m, url, body) => {
        const path = url.replace('http://s', '');
        posts.push({ path, body });
        if (path === '/v1/sync/reconcile') {
          return { status: 200, json: { status: 'noop', active_commit: 'c', manifest_hash: 'm',
            conversation_id: opts.conversation?.() ?? 'v' } };
        }
        return handler(path, body);
      },
      warn: () => {}, debug: () => {}, now: () => performance.now(),
    };
    return { h, posts };
  }
  const sidecar = (store: Set<string>) => (path: string, body: any): HttpResult => {
    if (path === '/v1/retrieve') return { status: 200, json: { freshness: 'fresh', packet: { text: '' } } };
    if (path === '/v1/sync/canon') {
      for (const [h] of Object.entries(body.contents ?? {})) store.add(h);
      return { status: 200, json: { needed: body.entries.map((e: any) => e.hash).filter((h: string) => !store.has(h)) } };
    }
    return { status: 404, json: null };
  };
  const settle = (ms = 20) => new Promise((r) => setTimeout(r, ms));
  const canonPosts = (posts: { path: string; body: any }[]) => posts.filter((p) => p.path === '/v1/sync/canon');

  it('sends the canon the prompt holds and its manifest with the request, and the texts in the background once the card is known', async () => {
    const store = new Set<string>();
    const { h, posts } = host(sidecar(store), { delay: 30 });
    const adapter = createAdapter(h);
    await adapter.beforeRequest(prompt, 'model'); // the card is still being read: no manifest, no canon sync
    const first = posts.find((p) => p.path === '/v1/retrieve')!.body;
    expect([first.canon_held, first.canon_manifest_id]).toEqual([['lore:lore-world'], null]);
    await settle();
    expect(canonPosts(posts)).toHaveLength(0);
    await settle(40);
    await adapter.beforeRequest(more('again'), 'model');
    await settle();
    const second = posts.filter((p) => p.path === '/v1/retrieve')[1]!.body;
    expect(second.canon_held).toEqual(['card:desc', 'card:personality', 'lore:lore-world']);
    const sent = canonPosts(posts);
    expect(sent).toHaveLength(2); // the manifest, then the texts it asked for
    expect(await canonManifestId(sent[0]!.body.entries)).toBe(second.canon_manifest_id);
    expect(sent[0]!.body.contents).toBeUndefined();
    expect(typeof sent[0]!.body.observed_at).toBe('number');
    expect(Object.keys(sent[1]!.body.contents)).toHaveLength(sent[0]!.body.entries.length);
    await adapter.beforeRequest(more('third'), 'model');
    await settle();
    expect(canonPosts(posts)).toHaveLength(2); // unchanged: nothing sent
  });

  it('syncs canon for a cached packet too, and again for a conversation made anew after a delete', async () => {
    let conversation = 'v1';
    const { h, posts } = host(sidecar(new Set()), { conversation: () => conversation });
    const adapter = createAdapter(h);
    await adapter.beforeRequest(prompt, 'model');
    await settle();
    const before = canonPosts(posts).length;
    await adapter.beforeRequest(structuredClone(prompt), 'model'); // the same state: the cached packet
    await settle();
    expect(posts.filter((p) => p.path === '/v1/retrieve')).toHaveLength(1);
    expect(canonPosts(posts).length).toBeGreaterThanOrEqual(before); // observed; unchanged, so nothing new
    conversation = 'v2'; // the chat was deleted in the sidecar and synced again
    await adapter.beforeRequest(more('after delete'), 'model');
    await settle();
    expect(canonPosts(posts).length).toBeGreaterThan(before);
  });

  it('never reuses a cached packet after the canon changed or the prompt holds other canon', async () => {
    const { h, posts } = host(sidecar(new Set()), { delay: 30 });
    const adapter = createAdapter(h);
    const retrieves = () => posts.filter((p) => p.path === '/v1/retrieve').map((p) => p.body);
    const reroll = async (p = prompt) => { await adapter.beforeRequest(structuredClone(p), 'model'); await settle(); };
    await reroll(); // the card is still being read: no manifest
    await settle(40);
    await reroll(); // the same prompt once the card is known: its manifest, not the packet built without one
    expect(retrieves().map((b) => b.canon_manifest_id === null)).toEqual([true, false]);
    const n = retrieves().length;
    await reroll(); // unchanged: the cached packet
    expect(retrieves()).toHaveLength(n);
    (h.lorebook as any) = async () => [{ ...kaito, content: '카이토는 이제 정식 기사다.' }, world, folder, tunnel]; // an entry edited
    await reroll();
    expect(retrieves()).toHaveLength(n + 1);
    expect(retrieves()[n]!.canon_manifest_id).not.toBe(retrieves()[n - 1]!.canon_manifest_id);
    await reroll();
    expect(retrieves()).toHaveLength(n + 1); // the new canon is cached in turn
    (h.lorebook as any) = async () => [world, folder, tunnel]; // an entry removed
    await reroll();
    expect(retrieves()).toHaveLength(n + 2);
    h.currentChat = async () => structuredClone({ ...chat, note: '지금은 한여름 낮이다.' }); // the author's note edited
    await reroll();
    expect(retrieves()).toHaveLength(n + 3);
    await reroll([{ role: 'system', content: `${card.desc}\n${card.personality}` }, prompt[1]!]); // the same length, less canon
    expect(retrieves()).toHaveLength(n + 4);
    expect(retrieves()[n + 3]!.canon_held).toEqual(['card:desc', 'card:personality']);
  });

  it('never syncs an empty lorebook when reading it failed', async () => {
    let fail = false;
    const { h, posts } = host(sidecar(new Set()), { lorebook: async () => { if (fail) throw new Error('host'); return [kaito, world]; } });
    const adapter = createAdapter(h);
    await adapter.beforeRequest(prompt, 'model');
    await settle();
    const n = canonPosts(posts).length;
    fail = true;
    await adapter.beforeRequest(more('x'), 'model');
    await settle();
    expect(canonPosts(posts)).toHaveLength(n);
    expect(posts.filter((p) => p.path === '/v1/retrieve').at(-1)!.body.canon_held).toEqual([]);
  });

  it('sends no canon when the host has no lorebook call', async () => {
    const { h, posts } = host(sidecar(new Set()), { lorebook: async () => { throw new Error('no lorebook call on this host'); } });
    const adapter = createAdapter(h);
    await adapter.beforeRequest(prompt, 'model');
    await settle();
    await adapter.beforeRequest(more('y'), 'model');
    await settle();
    expect(canonPosts(posts)).toHaveLength(0);
  });

  it('uploads one manifest per chat at a time, the newest last', async () => {
    const store = new Set<string>();
    let release: () => void = () => {};
    const gate = new Promise<void>((r) => { release = r; });
    let calls = 0;
    const { h, posts } = host(async (path, body) => {
      if (path === '/v1/sync/canon' && calls++ === 0) await gate; // the first upload is slow
      return sidecar(store)(path, body);
    });
    const adapter = createAdapter(h);
    await adapter.beforeRequest(prompt, 'model');
    await settle();
    (h.lorebook as any) = async () => [kaito, world, folder, tunnel, market]; // the lorebook grew
    await adapter.beforeRequest(more('b'), 'model');
    await adapter.beforeRequest(more('c'), 'model');
    await settle();
    expect(canonPosts(posts)).toHaveLength(1); // the second waits for the first
    release();
    await settle(50);
    const manifests = canonPosts(posts).map((p) => p.body.entries.length);
    expect(manifests[0]).toBe(4 + 1 + 3); // four card fields, the note, the first lorebook
    expect(manifests.at(-1)).toBe(4 + 1 + 4); // the newest observation last
  });

  it('reads the card again when its description is no longer in the prompt (an edit, H19)', async () => {
    const { h } = host(sidecar(new Set()));
    const adapter = createAdapter(h);
    await adapter.beforeRequest(prompt, 'model');
    await settle();
    const reads = (h.card as any).mock.calls.length;
    await adapter.beforeRequest([{ role: 'system', content: '하나는 이제 열여섯 살이다.' }, { role: 'system', content: 'x' },
      prompt[1]!], 'model');
    await settle();
    expect((h.card as any).mock.calls.length).toBe(reads + 1);
  });

  it('stops trying against a sidecar without canon sync', async () => {
    const { h, posts } = host((path, body) => (path === '/v1/sync/canon' ? { status: 404, json: { detail: 'Not Found' } }
      : sidecar(new Set())(path, body)));
    const adapter = createAdapter(h);
    for (const extra of ['a', 'b', 'c']) {
      await adapter.beforeRequest(more(extra), 'model');
      await settle();
    }
    expect(canonPosts(posts)).toHaveLength(1);
  });
});
