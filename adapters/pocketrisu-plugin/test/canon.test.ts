import { describe, expect, it, vi } from 'vitest';
import { canonTexts, heldKeys, loreKey, type HostCard, type HostLoreEntry } from '../src/canon';
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
    expect(twins).toEqual([loreKey(tunnel), `${loreKey(tunnel)}.1`]);
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
});

describe('canon sync', () => {
  const prompt: PromptMessage[] = [
    { role: 'system', content: `${card.desc}\n${card.personality}\n${world.content}` },
    { role: 'user', content: '카이토는 어디 있어?' },
  ];
  function host(handler: (path: string, body: any) => HttpResult, cardFor: () => HostCard | null = () => card, delay = 0) {
    const posts: { path: string; body: any }[] = [];
    const h: HostPort = {
      settings: async () => ({ sidecarUrl: 'http://s', authToken: '', enabled: true, reservedMemoryTokens: 600, deadlineMs: 500,
        injectPosition: 'before_last_user', route: 'direct', language: 'en' }),
      currentChat: async () => structuredClone(chat),
      card: vi.fn(async () => {
        if (delay) await new Promise((r) => setTimeout(r, delay));
        return cardFor();
      }),
      lorebook: async () => [kaito, world, folder, tunnel],
      request: async (_m, url, body) => {
        const path = url.replace('http://s', '');
        posts.push({ path, body });
        return handler(path, body);
      },
      warn: () => {}, debug: () => {}, now: () => performance.now(),
    };
    return { h, posts };
  }
  const sidecar = (store: Set<string>) => (path: string, body: any): HttpResult => {
    if (path === '/v1/sync/reconcile') return { status: 200, json: { status: 'noop', active_commit: 'c', manifest_hash: 'm', conversation_id: 'v' } };
    if (path === '/v1/retrieve') return { status: 200, json: { freshness: 'fresh', packet: { text: '' } } };
    if (path === '/v1/sync/canon') {
      for (const [h] of Object.entries(body.contents ?? {})) store.add(h);
      return { status: 200, json: { needed: body.entries.map((e: any) => e.hash).filter((h: string) => !store.has(h)) } };
    }
    return { status: 404, json: null };
  };
  const settle = () => new Promise((r) => setTimeout(r, 20));

  it('sends which canon the prompt holds with the request, and the texts in the background once the card is known', async () => {
    const store = new Set<string>();
    const { h, posts } = host(sidecar(store), () => card, 30);
    const adapter = createAdapter(h);
    await adapter.beforeRequest(prompt, 'model'); // the card is still being read in the background: no canon sync
    const first = posts.find((p) => p.path === '/v1/retrieve')!.body;
    expect(first.canon_held).toEqual(['lore:lore-world']);
    await settle();
    expect(posts.filter((p) => p.path === '/v1/sync/canon')).toHaveLength(0);
    await new Promise((r) => setTimeout(r, 40));
    await adapter.beforeRequest(structuredClone([...prompt, { role: 'user', content: 'again' }]), 'model');
    await settle();
    expect(posts.filter((p) => p.path === '/v1/retrieve')[1]!.body.canon_held)
      .toEqual(['card:desc', 'card:personality', 'lore:lore-world']);
    const canonPosts = posts.filter((p) => p.path === '/v1/sync/canon');
    expect(canonPosts).toHaveLength(2); // the manifest, then the texts it asked for
    expect(canonPosts[0]!.body.contents).toBeUndefined();
    expect(Object.keys(canonPosts[1]!.body.contents)).toHaveLength(canonPosts[0]!.body.entries.length);
    expect(canonPosts[0]!.body.entries.map((e: any) => e.key)).toContain('card:desc');
    await adapter.beforeRequest(structuredClone([...prompt, { role: 'user', content: 'third' }]), 'model');
    await settle();
    expect(posts.filter((p) => p.path === '/v1/sync/canon')).toHaveLength(2); // unchanged: nothing sent
  });

  it('reads the card again when its description is no longer in the prompt (an edit, H19)', async () => {
    const { h } = host(sidecar(new Set()));
    const adapter = createAdapter(h);
    await adapter.beforeRequest(prompt, 'model');
    await settle();
    const reads = (h.card as any).mock.calls.length;
    await adapter.beforeRequest([{ role: 'system', content: '하나는 이제 열여섯 살이다.' }, { role: 'system', content: 'x' },
      prompt[1]!], 'model'); // another length: not the cached packet
    await settle();
    expect((h.card as any).mock.calls.length).toBe(reads + 1);
  });

  it('stops trying against a sidecar without canon sync', async () => {
    const { h, posts } = host((path, body) => (path === '/v1/sync/canon' ? { status: 404, json: { detail: 'Not Found' } }
      : sidecar(new Set())(path, body)));
    const adapter = createAdapter(h);
    for (const extra of ['a', 'b', 'c']) {
      await adapter.beforeRequest(structuredClone([...prompt, { role: 'user', content: extra }]), 'model');
      await settle();
    }
    expect(posts.filter((p) => p.path === '/v1/sync/canon')).toHaveLength(1);
  });
});
