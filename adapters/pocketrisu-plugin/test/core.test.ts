import { describe, expect, it, vi } from 'vitest';
import { createAdapter, personaOf, type HostPort, type HttpResult, type Settings } from '../src/core';
import { deadlineAdvice } from '../src/deadline';
import { DEFAULT_DEADLINE_MS } from '../src/form';
import type { ActivityEvent } from '../src/hud';
import { hasPacket } from '../src/prompt';
import type { HostChat, PromptMessage } from '../src/types';

const chat: HostChat = {
  id: 'chat-1',
  message: [
    { role: 'user', data: 'The lantern is hidden in the old archive.', chatId: 'u0' },
    { role: 'char', data: 'Noted.', chatId: 'c0', generationInfo: { generationId: 'c0' } },
    { role: 'user', data: 'Where did we hide the lantern?', chatId: 'u1' },
  ],
};
const prompt: PromptMessage[] = [
  { role: 'system', content: 'narrator' },
  { role: 'user', content: 'Where did we hide the lantern?' },
];
const PACKET = '<NarrativeMemory version="0" source="nmos">\n  <Excerpt turn="0" speaker="user">lantern</Excerpt>\n</NarrativeMemory>';

function fakeHost(handler: (path: string, body: any) => Promise<HttpResult> | HttpResult, overrides: Partial<Settings> = {}) {
  const calls: string[] = [];
  const warn = vi.fn();
  const host: HostPort = {
    settings: async () => ({ sidecarUrl: 'http://sidecar', authToken: 't', enabled: true, reservedMemoryTokens: 600,
      deadlineMs: 200, injectPosition: 'before_last_user', route: 'direct', language: 'ko', ...overrides }),
    currentChat: async () => structuredClone(chat),
    request: async (_method, url, body) => {
      const path = url.replace('http://sidecar', '');
      calls.push(path);
      return handler(path, body);
    },
    warn,
    debug: () => {},
    now: () => performance.now(),
  };
  return { host, calls, warn };
}

const happy = (path: string, body: any): HttpResult => {
  if (path === '/v1/sync/reconcile') {
    return { status: 200, json: { status: 'needs_bodies', active_commit: null, manifest_hash: 'm',
      needed_bodies: body.messages.map((m: any) => ({ host_logical_id: m.host_logical_id, revision_hash: m.revision_hash })) } };
  }
  if (path === '/v1/sync/bodies') {
    expect(body.bodies).toHaveLength(3);
    return { status: 200, json: { ok: true, reconcile: { status: 'applied', active_commit: 'commit-1', manifest_hash: 'm' } } };
  }
  if (path === '/v1/retrieve') {
    expect(body.active_commit).toBe('commit-1');
    expect(body.query).toBe('Where did we hide the lantern?');
    expect(body.in_context_ids).toEqual(['u1']);
    return { status: 200, json: { freshness: 'fresh', packet: { text: PACKET } } };
  }
  return { status: 404, json: null };
};

/** Sync answers at once; recall answers after `ms`. */
const slowRecall = (ms: number) => (path: string): Promise<HttpResult> | HttpResult =>
  path === '/v1/retrieve'
    ? new Promise((resolve) => setTimeout(() => resolve({ status: 200, json: { freshness: 'fresh', packet: { text: PACKET } } }), ms))
    : { status: 200, json: { status: 'noop', active_commit: 'c', manifest_hash: 'm', conversation_id: 'conv-1' } };

describe('beforeRequest', () => {
  it('reconciles, uploads bodies, retrieves once and injects', async () => {
    const { host, calls } = fakeHost(happy);
    const out = await createAdapter(host).beforeRequest(prompt, 'model');
    expect(calls).toEqual(['/v1/sync/reconcile', '/v1/sync/bodies', '/v1/retrieve']);
    expect(hasPacket(out)).toBe(true);
    expect(out[1]?.role).toBe('system');
  });

  it('keeps what the budget left out for the status tab, also for a cached packet (ADR 0036)', async () => {
    const memory = { offered: 15, cut: 4, fits_at: 1100 };
    const { host, calls } = fakeHost((path, body) => {
      const res = happy(path, body);
      return path === '/v1/retrieve' ? { status: 200, json: { ...(res.json as object), memory } } : res;
    });
    const adapter = createAdapter(host);
    await adapter.beforeRequest(prompt, 'model');
    expect((await adapter.status()).last).toMatchObject({ budgetTokens: 600, memory });
    await adapter.beforeRequest(structuredClone(prompt), 'model');  // a reroll of the same chat state: cached
    expect(calls.filter((c) => c === '/v1/retrieve')).toHaveLength(1);
    expect((await adapter.status()).last).toMatchObject({ budgetTokens: 600, memory });
  });

  it('keeps whether recall searched vectors for the status tab, also for a cached packet (PHASE-15 Q5)', async () => {
    const { host } = fakeHost((path, body) => {
      const res = happy(path, body);
      return path === '/v1/retrieve' ? { status: 200, json: { ...(res.json as object), vectors: 'fallback' } } : res;
    });
    const adapter = createAdapter(host);
    await adapter.beforeRequest(prompt, 'model');
    expect((await adapter.status()).last?.vectors).toBe('fallback');
    await adapter.beforeRequest(structuredClone(prompt), 'model');  // cached
    expect((await adapter.status()).last?.vectors).toBe('fallback');
    const old = createAdapter(fakeHost(happy).host);  // an older sidecar sends none
    await old.beforeRequest(structuredClone(prompt), 'model');
    expect((await old.status()).last?.vectors).toBeNull();
  });

  it('tells the sidecar its build with every sync (ADR 0037)', async () => {
    const builds: unknown[] = [];
    const { host } = fakeHost((path, body) => {
      if (path === '/v1/sync/reconcile') builds.push(body.plugin_build);
      if (path === '/v1/sync/bodies') builds.push(body.then_reconcile?.plugin_build);
      return happy(path, body);
    });
    await createAdapter(host).beforeRequest(prompt, 'model');
    expect(builds).toEqual(['dev', 'dev']);  // "dev" outside a build; the built file carries its hash
  });

  it('host retries of the injected prompt make no further calls (H2)', async () => {
    const { host, calls } = fakeHost(happy);
    const adapter = createAdapter(host);
    const first = await adapter.beforeRequest(prompt, 'model');
    const retry = await adapter.beforeRequest(first, 'model');
    expect(retry).toBe(first);
    const fallbackReset = await adapter.beforeRequest(structuredClone(prompt), 'model');  // formated re-cloned per fallback
    expect(hasPacket(fallbackReset)).toBe(true);
    expect(calls.filter((c) => c === '/v1/retrieve')).toHaveLength(1);
  });

  it('still syncs and injects when a reply in the prompt quotes the packet tag', async () => {
    const { host, calls } = fakeHost(happy);
    const quoted: PromptMessage[] = [
      prompt[0]!,
      { role: 'assistant', content: `${PACKET.split('\n')[0]} was in my notes.` },
      prompt[1]!,
    ];
    const out = await createAdapter(host).beforeRequest(quoted, 'model');
    expect(calls).toEqual(['/v1/sync/reconcile', '/v1/sync/bodies', '/v1/retrieve']);
    expect(out).toHaveLength(quoted.length + 1);
    expect(out.filter((m) => m.content === PACKET)).toHaveLength(1);
  });

  it('passes auxiliary requests through without any call (S11)', async () => {
    const { host, calls } = fakeHost(happy);
    const adapter = createAdapter(host);
    expect(await adapter.beforeRequest(prompt, 'submodel')).toBe(prompt);
    expect(await adapter.beforeRequest([{ role: 'user', content: 'summarize this' }], 'model')).toEqual([{ role: 'user', content: 'summarize this' }]);
    expect(calls).toEqual([]);
  });

  it('fails open with one warning when the sidecar is down', async () => {
    const { host, warn } = fakeHost(() => Promise.reject(new TypeError('Failed to fetch')));
    const adapter = createAdapter(host);
    expect(await adapter.beforeRequest(prompt, 'model')).toBe(prompt);
    expect(await adapter.beforeRequest(prompt, 'model')).toBe(prompt);  // retry: served from the miss cache
    expect(warn).toHaveBeenCalledTimes(1);
    expect((await adapter.status()).last).toMatchObject({ outcome: 'failed', error: expect.stringContaining('Failed to fetch') });
  });

  it('gives up at the deadline and returns the prompt unchanged', async () => {
    // Fake clock (audit A-19): the assertion is about the deadline, not about how busy the test machine is.
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'performance'] });
    try {
      let reached!: () => void;
      const called = new Promise<void>((r) => { reached = r; });
      const { host, warn } = fakeHost(() => { reached(); return new Promise<HttpResult>(() => {}); }, { deadlineMs: 50 });
      let settled = false;
      const out = createAdapter(host).beforeRequest(prompt, 'model').finally(() => { settled = true; });
      await called;
      await vi.advanceTimersByTimeAsync(49);
      expect(settled).toBe(false);
      await vi.advanceTimersByTimeAsync(1);
      expect(settled).toBe(true);
      expect(await out).toBe(prompt);
      expect(String(warn.mock.calls[0]?.[1])).toContain('deadline');
    } finally {
      vi.useRealTimers();
    }
  });

  it('gives up at the deadline when the host does not hand over the chat', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'performance'] });
    try {
      const { host, calls, warn } = fakeHost(happy, { deadlineMs: 50 });
      host.currentChat = () => new Promise<HostChat | null>(() => {});
      let settled = false;
      const out = createAdapter(host).beforeRequest(prompt, 'model').finally(() => { settled = true; });
      await vi.advanceTimersByTimeAsync(49);
      expect(settled).toBe(false);
      await vi.advanceTimersByTimeAsync(1);
      expect(settled).toBe(true);
      expect(await out).toBe(prompt);
      expect(calls).toEqual([]);
      expect(String(warn.mock.calls[0]?.[1])).toContain('deadline');
    } finally {
      vi.useRealTimers();
    }
  });

  it('gives up when the host never answers with the settings, without advice to raise the deadline', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'performance'] });
    try {
      const { host, calls, warn } = fakeHost(happy);
      const settings = host.settings;
      host.settings = () => new Promise<Settings>(() => {});
      let settled = false;
      const adapter = createAdapter(host);
      const out = adapter.beforeRequest(prompt, 'model').finally(() => { settled = true; });
      await vi.advanceTimersByTimeAsync(DEFAULT_DEADLINE_MS - 1);
      expect(settled).toBe(false);
      await vi.advanceTimersByTimeAsync(1);
      expect(await out).toBe(prompt);
      expect(calls).toEqual([]);
      expect(String(warn.mock.calls[0]?.[1])).toContain('settings');
      host.settings = settings;  // the panel reads them again later
      const { last } = await adapter.status();
      expect(last).toMatchObject({ outcome: 'failed', deadlineMs: 0 });
      expect(deadlineAdvice(last)).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it('records the deadline, and how long the request took when recall answers late', async () => {
    const { host } = fakeHost(slowRecall(150), { deadlineMs: 100 });
    const adapter = createAdapter(host);
    expect(await adapter.beforeRequest(prompt, 'model')).toBe(prompt);
    await new Promise((r) => setTimeout(r, 120));
    const { last } = await adapter.status();
    expect(last).toMatchObject({ outcome: 'failed', deadlineMs: 100 });
    expect(last!.neededMs).toBeGreaterThanOrEqual(140);
    expect(deadlineAdvice(last)).toMatchObject({ level: 'over', deadlineMs: 100 });
  });

  it('after a reply that went without memory for the deadline, pops up once per page', async () => {
    const { host } = fakeHost(slowRecall(150), { deadlineMs: 100 });
    const alert = vi.fn();
    const adapter = createAdapter({ ...host, alert });
    for (let i = 0; i < 2; i++) {
      await adapter.beforeRequest(structuredClone(prompt), 'model');
      await new Promise((r) => setTimeout(r, 120));
      adapter.onOutput({ chat, messageIndex: 1 });
      await new Promise((r) => setTimeout(r, 20));
    }
    expect(alert).toHaveBeenCalledTimes(1);
    expect(String(alert.mock.calls[0]?.[0])).toMatch(/100ms.*설정 탭/s);
  });

  it('does not pop up after a request that made it', async () => {
    const { host } = fakeHost(happy);
    const alert = vi.fn();
    const adapter = createAdapter({ ...host, alert });
    await adapter.beforeRequest(prompt, 'model');
    adapter.onOutput({ chat, messageIndex: 1 });
    await new Promise((r) => setTimeout(r, 20));
    expect(alert).not.toHaveBeenCalled();
  });

  it('does not inject stale or empty packets', async () => {
    const stale = (path: string, body: any) =>
      path === '/v1/retrieve'
        ? { status: 200, json: { freshness: 'stale', packet: { text: PACKET } } }
        : { status: 200, json: { status: 'noop', active_commit: 'c', manifest_hash: 'm' } };
    const { host } = fakeHost(stale);
    expect(hasPacket(await createAdapter(host).beforeRequest(prompt, 'model'))).toBe(false);
  });

  it('does nothing when disabled', async () => {
    const { host, calls } = fakeHost(happy, { enabled: false });
    expect(await createAdapter(host).beforeRequest(prompt, 'model')).toBe(prompt);
    expect(calls).toEqual([]);
  });

  it('sends nothing of a chat NMOS is off for and leaves its prompt as it is (ADR 0048)', async () => {
    const { host, calls } = fakeHost(happy, { offChats: ['other', 'chat-1'] });
    const card = vi.fn(async () => null);
    const lorebook = vi.fn(async () => []);
    const events: ActivityEvent[] = [];
    const adapter = createAdapter({ ...host, card, lorebook }, (e) => events.push(e));
    expect(await adapter.beforeRequest(prompt, 'model')).toBe(prompt);
    adapter.onOutput({ chat, messageIndex: 1 });
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(calls).toEqual([]);
    expect(card).not.toHaveBeenCalled();
    expect(lorebook).not.toHaveBeenCalled();
    expect(events).toEqual([{ type: 'request-start' },
      { type: 'request-end', outcome: 'chat-off', chars: 0, conversationId: null }]);
    expect((await adapter.status()).last).toBeNull();
  });

  it('works as before for a chat NMOS is not off for, and again once it is back on', async () => {
    const other = fakeHost(happy, { offChats: ['other'] });
    expect(hasPacket(await createAdapter(other.host).beforeRequest(prompt, 'model'))).toBe(true);
    const on = fakeHost(happy, { offChats: [] });
    expect(hasPacket(await createAdapter(on.host).beforeRequest(prompt, 'model'))).toBe(true);
    expect(on.calls).toEqual(['/v1/sync/reconcile', '/v1/sync/bodies', '/v1/retrieve']);
  });
});

describe('onOutput', () => {
  it('returns immediately and posts in the background', async () => {
    let release!: (r: HttpResult) => void;
    const { host, calls } = fakeHost(() => new Promise<HttpResult>((r) => { release = r; }));
    const result = createAdapter(host).onOutput({ chat, messageIndex: 1 });
    expect(result).toBeUndefined();
    await vi.waitFor(() => expect(calls).toEqual(['/v1/output']));
    release({ status: 202, json: {} });
  });
});

describe('packet cache', () => {
  it('never reuses a packet after any message in the chat changed', async () => {
    const { host, calls } = fakeHost(happy);
    let current = structuredClone(chat);
    host.currentChat = async () => structuredClone(current);
    const adapter = createAdapter(host);
    await adapter.beforeRequest(structuredClone(prompt), 'model');
    await adapter.beforeRequest(structuredClone(prompt), 'model');  // same state: cached
    expect(calls.filter((c) => c === '/v1/retrieve')).toHaveLength(1);
    current = structuredClone(chat);
    current.message[0]!.data = 'The lantern is hidden in the NEW archive.';  // out-of-context edit, same prompt
    await adapter.beforeRequest(structuredClone(prompt), 'model');
    expect(calls.filter((c) => c === '/v1/retrieve')).toHaveLength(2);
  });

  it('is emptied by a panel action, so a reroll after deleting the chat gets no old memory', async () => {
    const { host, calls } = fakeHost((path, body) => path.startsWith('/v1/conversations') ? { status: 200, json: {} } : happy(path, body));
    const adapter = createAdapter(host);
    await adapter.beforeRequest(structuredClone(prompt), 'model');
    await adapter.api('GET', '/v1/conversations');
    await adapter.beforeRequest(structuredClone(prompt), 'model');  // a read changes nothing: cached
    expect(calls.filter((c) => c === '/v1/retrieve')).toHaveLength(1);
    await adapter.api('POST', '/v1/conversations/x/delete', {});
    await adapter.beforeRequest(structuredClone(prompt), 'model');
    expect(calls.filter((c) => c === '/v1/retrieve')).toHaveLength(2);
  });
});

describe('body upload', () => {
  it('uploads bodies in chunks and reconciles with the last chunk', async () => {
    const big: HostChat = { id: 'big', message: Array.from({ length: 600 }, (_, i) => ({
      role: i % 2 ? 'char' : 'user', data: `message number ${i} with some text`, chatId: `m${i}` } as const)) };
    big.message.push({ role: 'user', data: 'Where did we hide the lantern?', chatId: 'last' });
    const chunks: number[] = [];
    const { host } = fakeHost((path, body) => {
      if (path === '/v1/sync/reconcile') return { status: 200, json: { status: 'needs_bodies', active_commit: null, manifest_hash: 'm',
        needed_bodies: body.messages.map((m: any) => ({ host_logical_id: m.host_logical_id, revision_hash: m.revision_hash })) } };
      if (path === '/v1/sync/bodies') {
        chunks.push(body.bodies.length);
        return { status: 200, json: { ok: true, reconcile: body.then_reconcile ? { status: 'applied', active_commit: 'c', manifest_hash: 'm' } : null } };
      }
      return { status: 200, json: { freshness: 'fresh', packet: { text: '' } } };
    }, { deadlineMs: 5000 });
    host.currentChat = async () => structuredClone(big);
    await createAdapter(host).beforeRequest(prompt, 'model');
    expect(chunks).toEqual([250, 250, 101]);
  });
});

describe('status', () => {
  it('reports connection, features and the last request', async () => {
    const { host } = fakeHost((path, body) => path === '/v1/health'
      ? { status: 200, json: { version: '0.1.0b1', features: { state: false, extraction: true, vectors: true } } }
      : happy(path, body));
    const adapter = createAdapter(host);
    expect((await adapter.status()).last).toBeNull();
    await adapter.beforeRequest(prompt, 'model');
    const s = await adapter.status();
    expect(s).toMatchObject({ connected: true, version: '0.1.0b1', enabled: true, language: 'ko',
      features: { extraction: true, vectors: true, state: false } });
    expect(s.last).toMatchObject({ outcome: 'injected', packetChars: PACKET.length, packet: PACKET });
  });

  it('shows the packet a cached reuse sent as the last request', async () => {
    const { host } = fakeHost(happy);
    const adapter = createAdapter(host);
    await adapter.beforeRequest(structuredClone(prompt), 'model');
    const first = (await adapter.status()).last!;
    await adapter.beforeRequest(structuredClone(prompt), 'model');  // same state: cached
    const again = (await adapter.status()).last!;
    expect(again).not.toBe(first);
    expect(again).toMatchObject({ outcome: 'injected', packet: PACKET });
  });

  it('reports an unreachable sidecar with the error', async () => {
    const { host } = fakeHost(() => Promise.reject(new TypeError('Failed to fetch')));
    const s = await createAdapter(host).status();
    expect(s.connected).toBe(false);
    expect(s.error).toContain('Failed to fetch');
  });
});

describe('conversation labels', () => {
  it('sends the chat name at once and the bot name once it resolved in the background', async () => {
    const reconciles: any[] = [];
    const { host } = fakeHost((path, body) => {
      if (path === '/v1/sync/reconcile') reconciles.push(body);
      return happy(path, body);
    });
    let resolve!: (name: string) => void;
    const lookups: string[] = [];
    host.characterName = (chatId) => { lookups.push(chatId); return new Promise((r) => { resolve = r; }); };
    host.currentChat = async () => ({ ...structuredClone(chat), name: '  벨로나 등대  ' });
    const adapter = createAdapter(host);
    await adapter.beforeRequest(prompt, 'model');
    expect(reconciles[0]).toMatchObject({ chat_name: '벨로나 등대' });
    expect(reconciles[0].character_name).toBeUndefined(); // never waited for on the request path
    resolve('하나');
    await new Promise((r) => setTimeout(r, 0));
    await adapter.beforeRequest([...prompt, { role: 'user', content: 'Where did we hide the lantern?' }], 'model');
    expect(reconciles.at(-1)).toMatchObject({ character_name: '하나', chat_name: '벨로나 등대' });
    expect(lookups).toEqual(['chat-1']); // cached, not looked up per request
  });
});

describe('persona name (ADR 0023)', () => {
  const personas = { personas: [{ id: 'p0', name: 'User' }, { id: 'p1', name: ' 타쿠미 ' }, { id: 'p2', name: '레이' }], selected: 1 };

  it('picks the chat-bound persona, else the selected one, as the host does', () => {
    expect(personaOf({ ...chat }, personas)).toBe('타쿠미');
    expect(personaOf({ ...chat, bindedPersona: 'p2' }, personas)).toBe('레이');
    expect(personaOf({ ...chat, bindedPersona: 'gone' }, personas)).toBe('타쿠미'); // host falls back too
    expect(personaOf({ ...chat }, { personas: [], selected: 0 })).toBeNull();
    expect(personaOf({ ...chat }, { personas: [{ name: '  ' }], selected: 0 })).toBeNull();
  });

  it('sends the persona name once read in the background, and never waits for it', async () => {
    const reconciles: any[] = [];
    const { host } = fakeHost((path, body) => {
      if (path === '/v1/sync/reconcile') reconciles.push(body);
      return happy(path, body);
    });
    let resolve!: (value: typeof personas | null) => void;
    let reads = 0;
    host.personas = () => { reads++; return new Promise((r) => { resolve = r; }); };
    const adapter = createAdapter(host);
    adapter.warmPersonas(); // at load: the host asks for its permission then, not during a request
    await adapter.beforeRequest(prompt, 'model');
    expect(reconciles[0].persona_name).toBeUndefined();
    resolve(personas);
    await new Promise((r) => setTimeout(r, 0));
    await adapter.beforeRequest([...prompt, { role: 'user', content: 'Where did we hide the lantern?' }], 'model');
    expect(reconciles.at(-1)).toMatchObject({ persona_name: '타쿠미' });
    expect(reads).toBe(1); // cached, not read per request
  });

  it('sends none when the host refuses or the read fails', async () => {
    const reconciles: any[] = [];
    const { host } = fakeHost((path, body) => {
      if (path === '/v1/sync/reconcile') reconciles.push(body);
      return happy(path, body);
    });
    host.personas = async () => { throw new Error('no getDatabase'); };
    const adapter = createAdapter(host);
    adapter.warmPersonas();
    await new Promise((r) => setTimeout(r, 0));
    await adapter.beforeRequest(prompt, 'model');
    expect(reconciles[0].persona_name).toBeUndefined();
    host.personas = async () => null; // permission refused
    const refused = createAdapter(host);
    refused.warmPersonas();
    await new Promise((r) => setTimeout(r, 0));
    await refused.beforeRequest([...prompt, { role: 'user', content: 'again' }], 'model');
    expect(reconciles.at(-1).persona_name).toBeUndefined();
  });
});

describe('route selection', () => {
  it('uses the browser for this machine and the PocketRisu server for anything else', async () => {
    const { routeFor } = await import('../src/host');
    expect(routeFor('http://127.0.0.1:8790', '')).toBe('direct');
    expect(routeFor('http://localhost:8790', 'auto')).toBe('direct');
    expect(routeFor('http://nmos-sidecar:8790', '')).toBe('server');
    expect(routeFor('http://192.168.0.10:8790', '')).toBe('server');
    expect(routeFor('http://192.168.0.10:8790', 'direct')).toBe('direct');
  });

  it('saves settings with a direct PUT to a localhost sidecar (the sidecar CORS must allow PUT)', async () => {
    const { routeFor } = await import('../src/host');
    const seen: Array<{ method: string; url: string; route: string; headers: Record<string, string> }> = [];
    const host: HostPort = {
      settings: async () => ({ sidecarUrl: 'http://localhost:8790', authToken: 't', enabled: true,
        reservedMemoryTokens: 600, deadlineMs: 200, injectPosition: 'before_last_user',
        route: routeFor('http://localhost:8790', ''), language: 'ko' }),
      currentChat: async () => null,
      request: async (method, url, _body, headers, _timeout, route) => {
        seen.push({ method, url, route, headers });
        return { status: 200, json: { queued_jobs: 0 } };
      },
      warn: () => {}, debug: () => {}, now: () => performance.now(),
    };
    await createAdapter(host).api('PUT', '/v1/config', { facts_limit: 3 });
    expect(seen).toEqual([{ method: 'PUT', url: 'http://localhost:8790/v1/config', route: 'direct',
      headers: { 'Content-Type': 'application/json', Authorization: 'Bearer t' } }]);
  });
});

describe('archive files (ADR 0050)', () => {
  function fileHost(answer: { status: number; bytes: ArrayBuffer | null; json: unknown } | null) {
    const seen: Array<{ url: string; headers: Record<string, string>; timeout: number; route: string }> = [];
    const host: HostPort = {
      settings: async () => ({ sidecarUrl: 'http://sidecar/', authToken: 't', enabled: true, reservedMemoryTokens: 600,
        deadlineMs: 200, injectPosition: 'before_last_user', route: 'server', language: 'ko' }),
      currentChat: async () => null,
      request: async () => { throw new Error('not a JSON call'); },
      ...(answer ? { requestFile: async (url: string, headers: Record<string, string>, timeout: number, route: string) => {
        seen.push({ url, headers, timeout, route });
        return answer;
      } } : {}),
      warn: () => {}, debug: () => {}, now: () => performance.now(),
    };
    return { host, seen };
  }

  it('fetches the archive with the token on the chosen route and returns its bytes', async () => {
    const bytes = new Uint8Array([80, 75, 3, 4]).buffer;
    const { host, seen } = fileHost({ status: 200, bytes, json: null });
    expect(await createAdapter(host).file('/v1/archive?conversation=c-1')).toBe(bytes);
    expect(seen).toEqual([{ url: 'http://sidecar/v1/archive?conversation=c-1', headers: { Authorization: 'Bearer t' },
      timeout: 300_000, route: 'server' }]);
  });

  it("says the sidecar's refusal, and a host that cannot fetch a file", async () => {
    const refused = fileHost({ status: 409, bytes: null, json: { detail: 'a row of source_revision holds a credential' } });
    await expect(createAdapter(refused.host).file('/v1/archive')).rejects
      .toThrow('/v1/archive -> HTTP 409: a row of source_revision holds a credential');
    await expect(createAdapter(fileHost(null).host).file('/v1/archive')).rejects.toThrow('cannot fetch a file');
  });
});

describe('activity events (progress display)', () => {
  const withConversation = (path: string, body: any): HttpResult => {
    const res = happy(path, body);
    if (path === '/v1/sync/bodies') (res.json as any).reconcile.conversation_id = 'conv-1';
    return res;
  };

  it('announces a main request and its outcome with the conversation', async () => {
    const { host } = fakeHost(withConversation);
    const events: ActivityEvent[] = [];
    await createAdapter(host, (e) => events.push(e)).beforeRequest(prompt, 'model');
    expect(events).toEqual([{ type: 'request-start' },
      { type: 'request-end', outcome: 'injected', chars: PACKET.length, conversationId: 'conv-1' }]);
  });

  it('says nothing for auxiliary requests or when memory is off', async () => {
    const events: ActivityEvent[] = [];
    await createAdapter(fakeHost(happy).host, (e) => events.push(e)).beforeRequest(prompt, 'submodel');
    await createAdapter(fakeHost(happy, { enabled: false }).host, (e) => events.push(e)).beforeRequest(prompt, 'model');
    expect(events).toEqual([]);
  });

  it('reports a failed request', async () => {
    const { host } = fakeHost(() => ({ status: 500, json: null }));
    const events: ActivityEvent[] = [];
    await createAdapter(host, (e) => events.push(e)).beforeRequest(prompt, 'model');
    expect(events[1]).toMatchObject({ type: 'request-end', outcome: 'failed', chars: 0, conversationId: null });
    expect((events[1] as { error: string }).error).toMatch(/HTTP 500/);
  });

  it('a throwing listener changes nothing', async () => {
    const { host } = fakeHost(happy);
    const out = await createAdapter(host, () => { throw new Error('boom'); }).beforeRequest(prompt, 'model');
    expect(hasPacket(out)).toBe(true);
  });

  it('announces a cached reuse too, and a prompt without a user turn is abandoned', async () => {
    const { host } = fakeHost(withConversation);
    const events: ActivityEvent[] = [];
    const adapter = createAdapter(host, (e) => events.push(e));
    await adapter.beforeRequest(prompt, 'model');
    await adapter.beforeRequest(structuredClone(prompt), 'model');
    expect(events.slice(2)).toEqual([{ type: 'request-start' },
      { type: 'request-end', outcome: 'injected', chars: PACKET.length, conversationId: 'conv-1' }]);
    events.length = 0;
    await adapter.beforeRequest([{ role: 'system', content: 'narrator' }, { role: 'user', content: 'unrelated text' }], 'model');
    expect(events).toEqual([{ type: 'request-start' }, { type: 'request-abandon' }]);
  });

  it('announces background work after a reply, for the conversation it knows', async () => {
    const { host } = fakeHost(withConversation);
    const events: ActivityEvent[] = [];
    const adapter = createAdapter(host, (e) => events.push(e));
    await adapter.beforeRequest(prompt, 'model');
    events.length = 0;
    adapter.onOutput({ chat, messageIndex: 1 });
    await vi.waitFor(() => expect(events).toEqual([{ type: 'background', conversationId: 'conv-1' }]));
  });
});
