import { describe, expect, it, vi } from 'vitest';
import type { HostCard, HostLoreEntry } from '../src/canon';
import { createAdapter, personaOf, type HostPort, type HttpResult, type Settings } from '../src/core';
import { deadlineAdvice } from '../src/deadline';
import { DEFAULT_DEADLINE_MS } from '../src/form';
import type { ActivityEvent } from '../src/hud';
import { MEMORY_MARKER } from '../src/placement';
import { GUARD_LINE, GUARD_RESERVE_TOKENS, hasPacket } from '../src/prompt';
import type { HostChat, HostMessage, PromptMessage } from '../src/types';

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

  it('says once per page that NMOS could not be reached, with what to fix (audit F25, F27)', async () => {
    const down = () => { throw new Error('TypeError: Failed to fetch'); };
    const { host } = fakeHost(down);
    const alert = vi.fn();
    const adapter = createAdapter({ ...host, alert });
    for (let i = 0; i < 2; i++) {
      expect(await adapter.beforeRequest(structuredClone(prompt), 'model')).toEqual(prompt);  // fail open
      adapter.onOutput({ chat, messageIndex: 1 });
      await new Promise((r) => setTimeout(r, 20));
    }
    expect(alert).toHaveBeenCalledTimes(1);
    expect(String(alert.mock.calls[0]?.[0])).toMatch(/연결할 수 없습니다.*트레이/s);

    const refused = fakeHost(() => ({ status: 401, json: { detail: 'unauthorized' } }));
    const tokenAlert = vi.fn();
    const other = createAdapter({ ...refused.host, alert: tokenAlert });
    await other.beforeRequest(structuredClone(prompt), 'model');
    other.onOutput({ chat, messageIndex: 1 });
    await new Promise((r) => setTimeout(r, 20));
    expect(String(tokenAlert.mock.calls[0]?.[0])).toMatch(/토큰/);
  });

  it('on a page without Web Crypto, skips the request in words and says so in the status (audit F24)', async () => {
    const { host, calls } = fakeHost(happy);
    const own = Object.getOwnPropertyDescriptor(globalThis.crypto, 'subtle');  // usually a getter on the prototype
    Object.defineProperty(globalThis.crypto, 'subtle', { value: undefined, configurable: true });
    try {
      const adapter = createAdapter(host);
      expect(await adapter.beforeRequest(structuredClone(prompt), 'model')).toEqual(prompt);
      const status = await adapter.status();
      expect(status.insecure).toBe(true);
      expect(status.last).toMatchObject({ outcome: 'failed', error: expect.stringMatching(/^insecure page/) });
      expect(calls.filter((c) => c.startsWith('/v1/sync'))).toEqual([]);
    } finally {
      if (own) Object.defineProperty(globalThis.crypto, 'subtle', own);
      else delete (globalThis.crypto as unknown as Record<string, unknown>).subtle;
    }
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

  it('never reuses a packet from another sidecar, token or budget', async () => {
    let settings: Settings = { sidecarUrl: 'http://sidecar', authToken: 't', enabled: true, reservedMemoryTokens: 600,
      deadlineMs: 200, injectPosition: 'before_last_user', route: 'direct', language: 'ko' };
    const retrieves: string[] = [];
    const host: HostPort = {
      settings: async () => settings,
      currentChat: async () => structuredClone(chat),
      request: async (_method, url, body, headers) => {
        const { origin, pathname } = new URL(url);
        if (pathname === '/v1/retrieve') retrieves.push(`${origin} ${headers.Authorization} ${body.budget_tokens}`);
        return happy(pathname, body);
      },
      warn: () => {}, debug: () => {}, now: () => performance.now(),
    };
    const adapter = createAdapter(host);
    const reroll = () => adapter.beforeRequest(structuredClone(prompt), 'model');
    await reroll();
    settings = { ...settings, sidecarUrl: 'http://sidecar/' };  // the same sidecar, written with a slash: cached
    await reroll();
    expect(retrieves).toEqual(['http://sidecar Bearer t 600']);
    settings = { ...settings, sidecarUrl: 'http://other-sidecar' };
    await reroll();
    settings = { ...settings, authToken: 'u' };
    await reroll();
    settings = { ...settings, reservedMemoryTokens: 900 };
    await reroll();
    expect(retrieves).toEqual(['http://sidecar Bearer t 600', 'http://other-sidecar Bearer t 600',
      'http://other-sidecar Bearer u 600', 'http://other-sidecar Bearer u 900']);
    settings = { ...settings, route: 'server' };  // the PocketRisu server's localhost is not the browser's
    await reroll();
    expect(retrieves).toHaveLength(5);
    settings = { ...settings, deadlineMs: 300 };  // how long it may take does not change the budget: cached
    await reroll();
    expect(retrieves).toHaveLength(5);
    settings = { ...settings, injectPosition: 'end' };  // post-turn placement lowers budget by GUARD_RESERVE_TOKENS: misses cache
    await reroll();
    expect(retrieves).toHaveLength(6);
    expect(retrieves.at(-1)).toBe('http://other-sidecar Bearer u 860');
    await reroll();  // cached at the reduced budget
    expect(retrieves).toHaveLength(6);
  });

  it('never reuses a packet for a prompt of the same length that holds other messages', async () => {
    const { host, calls } = fakeHost((path, body) => path === '/v1/retrieve'
      ? { status: 200, json: { freshness: 'fresh', packet: { text: PACKET } } } : happy(path, body));
    const adapter = createAdapter(host);
    const older = chat.message[0]!.data as string;
    await adapter.beforeRequest([{ role: 'system', content: 'narrator' }, prompt[1]!], 'model');
    await adapter.beforeRequest([{ role: 'system', content: older }, prompt[1]!], 'model');  // an older turn now in it
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

  it('neither caches nor injects a packet fetched while a panel action ran', async () => {
    let release!: () => void;
    const gate = new Promise<void>((r) => { release = r; });
    const { host, calls } = fakeHost(async (path, body) => {
      if (path.startsWith('/v1/conversations')) return { status: 200, json: {} };
      if (path === '/v1/retrieve' && calls.filter((c) => c === '/v1/retrieve').length === 1) await gate;
      return happy(path, body);
    });
    const adapter = createAdapter(host);
    const pending = adapter.beforeRequest(structuredClone(prompt), 'model');
    await vi.waitFor(() => expect(calls).toContain('/v1/retrieve'));
    await adapter.api('POST', '/v1/conversations/x/delete', {});  // the chat deleted while its memory was fetched
    release();
    expect(hasPacket(await pending)).toBe(false);  // fail open: the prompt as it was
    expect((await adapter.status()).last).toMatchObject({ outcome: 'failed', error: 'memory changed during this request' });
    expect(hasPacket(await adapter.beforeRequest(structuredClone(prompt), 'model'))).toBe(true);
    expect(calls.filter((c) => c === '/v1/retrieve')).toHaveLength(2);  // asked again, not the packet from before
  });

  it('is emptied again when a panel action that timed out answers late', async () => {
    let answer!: (r: HttpResult) => void;
    const { host, calls } = fakeHost((path, body) => path.startsWith('/v1/conversations')
      ? new Promise<HttpResult>((r) => { answer = r; }) : happy(path, body));
    const adapter = createAdapter(host);
    await expect(adapter.api('POST', '/v1/conversations/x/delete', {}, 20)).rejects.toThrow(/deadline/);
    await adapter.beforeRequest(structuredClone(prompt), 'model');  // before the sidecar applied the delete
    answer({ status: 200, json: {} });
    await new Promise((r) => setTimeout(r, 0));
    await adapter.beforeRequest(structuredClone(prompt), 'model');
    expect(calls.filter((c) => c === '/v1/retrieve')).toHaveLength(2);
  });

  it('is emptied by a panel action whose answer failed, since the sidecar may have applied it', async () => {
    const { host, calls } = fakeHost((path, body) => path.startsWith('/v1/conversations') ? { status: 502, json: null } : happy(path, body));
    const adapter = createAdapter(host);
    await adapter.beforeRequest(structuredClone(prompt), 'model');
    await expect(adapter.api('POST', '/v1/conversations/x/delete', {})).rejects.toThrow(/HTTP 502/);
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

describe('host-rewritten replies', () => {
  it('sends the text the host shows, not the generated swipe, and says so once on the HUD', async () => {
    const rewrittenChat: HostChat = { id: 'rw', message: [
      { role: 'user', data: 'Hello there', chatId: 'u0' },
      // Generated with 9월 18일, then a trigger rewrote `data`; the swipe still holds the generated reply.
      { role: 'char', data: 'Reply. [Status:date=9월 4일]', swipes: ['First.', 'Reply. [Status:date=9월 18일]'], swipeId: 1,
        chatId: 'c1', generationInfo: { generationId: 'c1' } },
      { role: 'user', data: 'Where did we hide the lantern?', chatId: 'u1' },
    ] };
    const sent: any[] = [];
    let known = false;
    const { host } = fakeHost((path, body) => {
      if (path === '/v1/sync/reconcile') {
        return { status: 200, json: known ? { status: 'noop', active_commit: 'c', manifest_hash: 'm' }
          : { status: 'needs_bodies', active_commit: null, manifest_hash: 'm', needed_bodies: body.messages.map((m: any) =>
            ({ host_logical_id: m.host_logical_id, revision_hash: m.revision_hash })) } };
      }
      if (path === '/v1/sync/bodies') {
        sent.push(...body.bodies); known = true;
        return { status: 200, json: { ok: true, reconcile: { status: 'applied', active_commit: 'c', manifest_hash: 'm' } } };
      }
      return { status: 200, json: { freshness: 'fresh', packet: { text: PACKET } } };
    }, { deadlineMs: 5000 });
    host.currentChat = async () => structuredClone(rewrittenChat);
    const events: ActivityEvent[] = [];
    const adapter = createAdapter(host, (e) => events.push(e));
    await adapter.beforeRequest(prompt, 'model');
    expect(sent.find((b) => b.host_logical_id === 'c1').content).toBe('Reply. [Status:date=9월 4일]');
    expect(events.at(-1)).toMatchObject({ type: 'request-end', outcome: 'injected', rewritten: 1 });
    events.length = 0;
    await adapter.beforeRequest([...prompt, { role: 'user', content: 'Where did we hide the lantern?' }], 'model');
    // Already known to the sidecar: no body is sent and nothing is announced again.
    expect(events.at(-1)).not.toHaveProperty('rewritten');
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

  it('never reuses a packet after the chat\'s persona changed', async () => {
    const reconciles: any[] = [];
    const { host } = fakeHost((path, body) => {
      if (path === '/v1/sync/reconcile') reconciles.push(body);
      return happy(path, body);
    });
    let current = structuredClone(chat);
    host.currentChat = async () => structuredClone(current);
    host.personas = async () => personas;
    const adapter = createAdapter(host);
    adapter.warmPersonas();
    await new Promise((r) => setTimeout(r, 0));
    await adapter.beforeRequest(structuredClone(prompt), 'model');
    await adapter.beforeRequest(structuredClone(prompt), 'model');  // cached
    expect(reconciles.map((r) => r.persona_name)).toEqual(['타쿠미']);
    current = { ...current, bindedPersona: 'p2' };  // the chat bound to another persona: no message changed
    await adapter.beforeRequest(structuredClone(prompt), 'model');
    expect(reconciles.map((r) => r.persona_name)).toEqual(['타쿠미', '레이']);
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
      { type: 'request-end', outcome: 'injected', chars: PACKET.length, conversationId: 'conv-1', vectors: null }]);
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

  it('announces a cached reuse too, and says when a prompt without the user turn is skipped', async () => {
    const { host, warn } = fakeHost(withConversation);
    const events: ActivityEvent[] = [];
    const adapter = createAdapter(host, (e) => events.push(e));
    await adapter.beforeRequest(prompt, 'model');
    await adapter.beforeRequest(structuredClone(prompt), 'model');
    expect(events.slice(2)).toEqual([{ type: 'request-start' },
      { type: 'request-end', outcome: 'injected', chars: PACKET.length, conversationId: 'conv-1', reused: true, vectors: null }]);
    events.length = 0;
    const unrelated = [{ role: 'system', content: 'narrator' }, { role: 'user', content: 'unrelated text' }] as PromptMessage[];
    expect(await adapter.beforeRequest(unrelated, 'model')).toEqual(unrelated);
    // Not silent: a skipped request shows on the HUD and the status tab, with the reason in the console.
    expect(events).toEqual([{ type: 'request-start' }, { type: 'request-end', outcome: 'skipped', chars: 0,
      error: expect.stringContaining('not found in the prompt'), conversationId: 'conv-1' }]);
    expect((await adapter.status()).last).toMatchObject({ outcome: 'skipped', packetChars: 0 });
    expect(warn).toHaveBeenCalledWith(expect.stringContaining('memory skipped'), expect.stringContaining('not found'),
      expect.objectContaining({ promptMessages: 2 }));
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

describe('[NMOS.memory] (PHASE-60 S2.3)', () => {
  const markedPrompt = (): PromptMessage[] => [
    { role: 'system', content: `narrator\n${MEMORY_MARKER}\nend` },
    { role: 'user', content: `Where did we hide the lantern? ${MEMORY_MARKER}` },
  ];
  const strippedPrompt: PromptMessage[] = [
    { role: 'system', content: 'narrator\n\nend' },
    { role: 'user', content: 'Where did we hide the lantern? ' },
  ];

  it('strips [NMOS.memory] on every skip, early return, and failure path without placing a packet', async () => {
    // mode !== 'model'
    {
      const { host, calls } = fakeHost(happy);
      const out = await createAdapter(host).beforeRequest(markedPrompt(), 'submodel');
      expect(out).toEqual(strippedPrompt);
      expect(hasPacket(out)).toBe(false);
      expect(calls).toEqual([]);
    }
    // hasPacket retry with a stray marker
    {
      const { host, calls } = fakeHost(happy);
      const retryPrompt: PromptMessage[] = [
        { role: 'system', content: PACKET },
        { role: 'user', content: `Where did we hide the lantern? ${MEMORY_MARKER}` },
      ];
      const out = await createAdapter(host).beforeRequest(retryPrompt, 'model');
      expect(out).toEqual([
        { role: 'system', content: PACKET },
        { role: 'user', content: 'Where did we hide the lantern? ' },
      ]);
      expect(calls).toEqual([]);
    }
    // enabled: false
    {
      const { host, calls } = fakeHost(happy, { enabled: false });
      const out = await createAdapter(host).beforeRequest(markedPrompt(), 'model');
      expect(out).toEqual(strippedPrompt);
      expect(hasPacket(out)).toBe(false);
      expect(calls).toEqual([]);
    }
    // sidecarUrl: ''
    {
      const { host, calls } = fakeHost(happy, { sidecarUrl: '' });
      const out = await createAdapter(host).beforeRequest(markedPrompt(), 'model');
      expect(out).toEqual(strippedPrompt);
      expect(hasPacket(out)).toBe(false);
      expect(calls).toEqual([]);
    }
    // insecure page (crypto.subtle missing)
    {
      const { host, calls } = fakeHost(happy);
      const own = Object.getOwnPropertyDescriptor(globalThis.crypto, 'subtle');
      Object.defineProperty(globalThis.crypto, 'subtle', { value: undefined, configurable: true });
      try {
        const out = await createAdapter(host).beforeRequest(markedPrompt(), 'model');
        expect(out).toEqual(strippedPrompt);
        expect(hasPacket(out)).toBe(false);
        expect(calls).toEqual([]);
      } finally {
        if (own) Object.defineProperty(globalThis.crypto, 'subtle', own);
        else delete (globalThis.crypto as unknown as Record<string, unknown>).subtle;
      }
    }
    // currentChat returning { message: [] } without id
    {
      const { host, calls } = fakeHost(happy);
      host.currentChat = async () => ({ message: [] });
      const out = await createAdapter(host).beforeRequest(markedPrompt(), 'model');
      expect(out).toEqual(strippedPrompt);
      expect(hasPacket(out)).toBe(false);
      expect(calls).toEqual([]);
    }
    // chat in offChats
    {
      const { host, calls } = fakeHost(happy, { offChats: ['chat-1'] });
      const out = await createAdapter(host).beforeRequest(markedPrompt(), 'model');
      expect(out).toEqual(strippedPrompt);
      expect(hasPacket(out)).toBe(false);
      expect(calls).toEqual([]);
    }
    // user turn not found in prompt
    {
      const { host, calls } = fakeHost(happy);
      const unmatched: PromptMessage[] = [
        { role: 'system', content: `narrator ${MEMORY_MARKER}` },
        { role: 'user', content: `unrelated ${MEMORY_MARKER}` },
      ];
      const out = await createAdapter(host).beforeRequest(unmatched, 'model');
      expect(out).toEqual([
        { role: 'system', content: 'narrator ' },
        { role: 'user', content: 'unrelated ' },
      ]);
      expect(hasPacket(out)).toBe(false);
      expect(calls).toEqual([]);
    }
    // /v1/retrieve answering 500
    {
      const { host } = fakeHost((path, body) => (path === '/v1/retrieve' ? { status: 500, json: null } : happy(path, body)));
      const out = await createAdapter(host).beforeRequest(markedPrompt(), 'model');
      expect(out).toEqual(strippedPrompt);
      expect(hasPacket(out)).toBe(false);
    }
    // request throwing (sidecar down)
    {
      const { host } = fakeHost(() => Promise.reject(new TypeError('Failed to fetch')));
      const out = await createAdapter(host).beforeRequest(markedPrompt(), 'model');
      expect(out).toEqual(strippedPrompt);
      expect(hasPacket(out)).toBe(false);
    }
    // recall slower than the deadline
    {
      vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'performance'] });
      try {
        const { host } = fakeHost(slowRecall(150), { deadlineMs: 50 });
        const pending = createAdapter(host).beforeRequest(markedPrompt(), 'model');
        await vi.advanceTimersByTimeAsync(50);
        const out = await pending;
        expect(out).toEqual(strippedPrompt);
        expect(hasPacket(out)).toBe(false);
      } finally {
        vi.useRealTimers();
      }
    }
  });

  it('replaces the first [NMOS.memory] in a system message, removes later markers, and inserts no extra message', async () => {
    const { host } = fakeHost(happy);
    const input = markedPrompt();
    const out = await createAdapter(host).beforeRequest(input, 'model');
    expect(out).toHaveLength(input.length);
    expect(out).toEqual([
      { role: 'system', content: `narrator\n${PACKET}\nend` },
      { role: 'user', content: 'Where did we hide the lantern? ' },
    ]);
  });

  it('uses full budget with no guard before the user turn, and adds the guard with reduced budget after it', async () => {
    const budgets: number[] = [];
    const { host } = fakeHost((path, body) => {
      if (path === '/v1/retrieve') budgets.push(body.budget_tokens);
      return happy(path, body);
    }, { reservedMemoryTokens: 600 });
    const adapter = createAdapter(host);

    // Marker in a system message before the user turn: no guard, full budget.
    const beforeInput: PromptMessage[] = [
      { role: 'system', content: `narrator\n${MEMORY_MARKER}` },
      { role: 'user', content: 'Where did we hide the lantern?' },
    ];
    const beforeOut = await adapter.beforeRequest(beforeInput, 'model');
    expect(beforeOut).toEqual([
      { role: 'system', content: `narrator\n${PACKET}` },
      { role: 'user', content: 'Where did we hide the lantern?' },
    ]);
    expect(budgets).toEqual([600]);
    expect((await adapter.status()).last?.budgetTokens).toBe(600);

    // Marker in a user-role message after the user turn: guard line right after </NarrativeMemory>, reduced budget.
    // Moving the marker across the user turn changes the effective budget, so it misses the cache.
    const afterInput: PromptMessage[] = [
      { role: 'system', content: 'narrator' },
      { role: 'user', content: `Where did we hide the lantern?\n${MEMORY_MARKER}` },
    ];
    const afterOut = await adapter.beforeRequest(afterInput, 'model');
    expect(afterOut).toEqual([
      { role: 'system', content: 'narrator' },
      { role: 'user', content: `Where did we hide the lantern?\n${PACKET}\n${GUARD_LINE}` },
    ]);
    expect(budgets).toEqual([600, 600 - GUARD_RESERVE_TOKENS]);
    expect((await adapter.status()).last?.budgetTokens).toBe(600 - GUARD_RESERVE_TOKENS);

    // Cached reuse of the post-turn prompt keeps the reduced budget on LastRequest and still appends the guard.
    const afterCached = await adapter.beforeRequest(structuredClone(afterInput), 'model');
    expect(afterCached).toEqual(afterOut);
    expect(budgets).toEqual([600, 600 - GUARD_RESERVE_TOKENS]);
    expect((await adapter.status()).last?.budgetTokens).toBe(600 - GUARD_RESERVE_TOKENS);
  });

  it('places the packet into a multipart message text part without disturbing other parts', async () => {
    const budgets: number[] = [];
    const { host } = fakeHost((path, body) => {
      if (path === '/v1/retrieve') budgets.push(body.budget_tokens);
      return happy(path, body);
    }, { reservedMemoryTokens: 600 });
    const imagePart = { type: 'image_url', image_url: { url: 'https://example.invalid/harbor.png' } };
    const input: PromptMessage[] = [
      { role: 'system', content: 'narrator' },
      {
        role: 'user',
        content: [
          { type: 'text', text: 'Where did we hide the lantern?' },
          imagePart,
          { type: 'text', text: `Notes:\n${MEMORY_MARKER}\nDone.` },
        ],
      },
    ];
    const out = await createAdapter(host).beforeRequest(input, 'model');
    expect(out).toHaveLength(2);
    expect(out[1]?.content).toEqual([
      { type: 'text', text: 'Where did we hide the lantern?' },
      imagePart,
      { type: 'text', text: `Notes:\n${PACKET}\n${GUARD_LINE}\nDone.` },
    ]);
    expect(budgets).toEqual([600 - GUARD_RESERVE_TOKENS]);
  });

  it('removes the marker and places nothing when the sidecar returns an empty packet', async () => {
    const { host } = fakeHost((path, body) => (path === '/v1/retrieve'
      ? { status: 200, json: { freshness: 'fresh', packet: { text: '' } } }
      : happy(path, body)));
    const out = await createAdapter(host).beforeRequest(markedPrompt(), 'model');
    expect(out).toEqual(strippedPrompt);
    expect(hasPacket(out)).toBe(false);
  });

  it('places injectPosition=end before a trailing assistant prefill with the guard line and reduced budget', async () => {
    const budgets: number[] = [];
    const { host } = fakeHost((path, body) => {
      if (path === '/v1/retrieve') budgets.push(body.budget_tokens);
      return happy(path, body);
    }, { injectPosition: 'end', reservedMemoryTokens: 600 });
    const withPrefill: PromptMessage[] = [
      { role: 'system', content: 'narrator' },
      { role: 'user', content: 'Where did we hide the lantern?' },
      { role: 'assistant', content: '세라 paused by the door.' },
    ];
    const out = await createAdapter(host).beforeRequest(withPrefill, 'model');
    expect(out).toEqual([
      { role: 'system', content: 'narrator' },
      { role: 'user', content: 'Where did we hide the lantern?' },
      { role: 'system', content: `${PACKET}\n${GUARD_LINE}` },
      { role: 'assistant', content: '세라 paused by the door.' },
    ]);
    expect(budgets).toEqual([600 - GUARD_RESERVE_TOKENS]);
  });

  it('keeps before_last_user without a marker identical to existing output (no guard, full budget)', async () => {
    const budgets: number[] = [];
    const { host } = fakeHost((path, body) => {
      if (path === '/v1/retrieve') budgets.push(body.budget_tokens);
      return happy(path, body);
    }, { injectPosition: 'before_last_user', reservedMemoryTokens: 600 });
    const out = await createAdapter(host).beforeRequest(prompt, 'model');
    expect(out).toEqual([
      { role: 'system', content: 'narrator' },
      { role: 'system', content: PACKET },
      { role: 'user', content: 'Where did we hide the lantern?' },
    ]);
    expect(budgets).toEqual([600]);
  });

  it('observes canon on the host prompt before marker replacement so canon_held is unchanged (A17)', async () => {
    const card: HostCard = { name: '하나', desc: '하나는 항구 마을 등대지기의 딸이다.', personality: '', scenario: '',
      firstMessage: '' };
    const runWithLore = async (entryContent: string) => {
      const lore: HostLoreEntry[] = [
        { id: 'lore-slot', key: '', comment: 'slot', content: entryContent, mode: 'constant', alwaysActive: true },
      ];
      let held: string[] | null = null;
      const { host } = fakeHost((path, body) => {
        if (path === '/v1/sync/reconcile') return { status: 200, json: { status: 'noop', active_commit: 'c', manifest_hash: 'm', conversation_id: 'conv-1' } };
        if (path === '/v1/sync/canon') return { status: 200, json: { needed: [] } };
        if (path === '/v1/retrieve') {
          held = body.canon_held;
          return { status: 200, json: { freshness: 'fresh', packet: { text: PACKET } } };
        }
        return happy(path, body);
      });
      host.card = async () => card;
      host.lorebook = async () => lore;
      const adapter = createAdapter(host);
      const p: PromptMessage[] = [
        { role: 'system', content: `${card.desc}\n${entryContent}` },
        { role: 'user', content: 'Where did we hide the lantern?' },
      ];
      const out = await adapter.beforeRequest(p, 'model');
      return { held, out };
    };

    const withMarker = await runWithLore(`세라는 등대를 지킨다.\n${MEMORY_MARKER}`);
    const withoutMarker = await runWithLore('세라는 등대를 지킨다.');
    expect(withMarker.held).toContain('lore:lore-slot');
    expect(withMarker.held).toEqual(withoutMarker.held);
    expect(withMarker.out[0]?.content).toBe(`${card.desc}\n세라는 등대를 지킨다.\n${PACKET}`);
  });

  it('is idempotent across three chained retry calls in every placement mode (R5)', async () => {
    const cases: Array<{ name: string; position: Settings['injectPosition']; makePrompt: () => PromptMessage[] }> = [
      {
        name: 'marker in user-role message',
        position: 'before_last_user',
        makePrompt: () => [
          { role: 'system', content: 'narrator' },
          { role: 'user', content: `Where did we hide the lantern?\n${MEMORY_MARKER}` },
        ],
      },
      {
        name: 'marker in multipart message',
        position: 'before_last_user',
        makePrompt: () => [
          { role: 'system', content: 'narrator' },
          {
            role: 'user',
            content: [
              { type: 'text', text: 'Where did we hide the lantern?' },
              { type: 'image_url', image_url: { url: 'https://example.invalid/harbor.png' } },
              { type: 'text', text: `Notes:\n${MEMORY_MARKER}` },
            ],
          },
        ],
      },
      {
        name: 'marker in system message',
        position: 'before_last_user',
        makePrompt: () => [
          { role: 'system', content: `narrator\n${MEMORY_MARKER}` },
          { role: 'user', content: 'Where did we hide the lantern?' },
        ],
      },
      {
        name: 'no marker with before_last_user',
        position: 'before_last_user',
        makePrompt: () => structuredClone(prompt),
      },
      {
        name: 'no marker with end',
        position: 'end',
        makePrompt: () => [
          { role: 'system', content: 'narrator' },
          { role: 'user', content: 'Where did we hide the lantern?' },
          { role: 'assistant', content: '세라 stepped forward.' },
        ],
      },
    ];

    for (const c of cases) {
      let counter = 0;
      let settingsReads = 0;
      const { host, calls } = fakeHost((path, body) => {
        if (path === '/v1/retrieve') {
          counter += 1;
          const pkt = `<NarrativeMemory version="0" source="nmos">\n  <Excerpt turn="0" speaker="user">lantern #${counter} (${c.name})</Excerpt>\n</NarrativeMemory>`;
          return { status: 200, json: { freshness: 'fresh', packet: { text: pkt } } };
        }
        return happy(path, body);
      }, { injectPosition: c.position });
      const origSettings = host.settings;
      host.settings = () => { settingsReads += 1; return origSettings(); };
      const events: ActivityEvent[] = [];
      const adapter = createAdapter(host, (e) => events.push(e));

      const out1 = await adapter.beforeRequest(c.makePrompt(), 'model');
      const eventsAfterFirst = events.length;
      const out2 = await adapter.beforeRequest(out1, 'model');
      const out3 = await adapter.beforeRequest(out2, 'model');

      expect(out2, c.name).toBe(out1);
      expect(out3, c.name).toBe(out2);
      expect(out2, c.name).toEqual(out1);
      expect(out3, c.name).toEqual(out1);
      expect(calls.filter((p) => p === '/v1/retrieve'), c.name).toHaveLength(1);
      expect(settingsReads, c.name).toBe(1);
      expect(events.length, c.name).toBe(eventsAfterFirst);
    }
  });

  it('does not memoise a pass-through failure and expires retry memo entries after 120s (with holdsText fallback)', async () => {
    // 1) Pass-through (retrieve 500) is NOT memoised: after the 30s failure cache expires, retrieve runs again.
    {
      let now = 1_000;
      let fails = true;
      const { host, calls } = fakeHost((path, body) => {
        if (path === '/v1/retrieve' && fails) return { status: 500, json: null };
        return happy(path, body);
      });
      host.now = () => now;
      const adapter = createAdapter(host);

      const first = await adapter.beforeRequest(structuredClone(prompt), 'model');
      expect(first).toEqual(prompt);
      expect(calls.filter((p) => p === '/v1/retrieve')).toHaveLength(1);

      now += 31_000; // past FAILURE_TTL_MS (30s), still inside RETRY_MEMO_TTL_MS (120s)
      fails = false;
      const second = await adapter.beforeRequest(structuredClone(prompt), 'model');
      expect(calls.filter((p) => p === '/v1/retrieve')).toHaveLength(2);
      expect(hasPacket(second)).toBe(true);
    }

    // 2) Memo expires after 120s; even after expiry, holdsText stops double-placing the same packet.
    {
      let now = 10_000;
      let settingsReads = 0;
      const { host, calls } = fakeHost(happy);
      host.now = () => now;
      const origSettings = host.settings;
      host.settings = () => { settingsReads += 1; return origSettings(); };
      const adapter = createAdapter(host);

      const userMarked: PromptMessage[] = [
        { role: 'system', content: 'narrator' },
        { role: 'user', content: `Where did we hide the lantern?\n${MEMORY_MARKER}` },
      ];
      const out1 = await adapter.beforeRequest(userMarked, 'model');
      expect(settingsReads).toBe(1);
      expect(calls.filter((p) => p === '/v1/retrieve')).toHaveLength(1);

      // Still live at 119.999s: memo hit, no settings read.
      now += 119_999;
      const out2 = await adapter.beforeRequest(out1, 'model');
      expect(out2).toBe(out1);
      expect(settingsReads).toBe(1);

      // Past 120s: memo entry expired -> reaches settings again. Tier 1: the packet the marker put in the user block is
      // now seen by the retry guard (`hasPacket` with the chat), so recall is not reached again (it was before, and
      // holdsText kept the packet single); no second packet either way.
      now += 2;
      const out3 = await adapter.beforeRequest(out1, 'model');
      expect(settingsReads).toBe(2);
      expect(calls.filter((p) => p === '/v1/retrieve')).toHaveLength(1);
      expect(out3).toEqual(out1);
      expect(hasPacket(out3)).toBe(false); // no extra system packet injected

      // A further call with out1 is the same retry: no call, no second packet.
      const out4 = await adapter.beforeRequest(out1, 'model');
      expect(calls.filter((p) => p === '/v1/retrieve')).toHaveLength(1);
      expect(out4).toEqual(out1);
      expect(hasPacket(out4)).toBe(false);
    }
  });

  it('places a packet that quotes [NMOS.memory] once across three retries past the memo', async () => {
    // Canon text may hold the literal marker; the placed text has it removed, so the retry guard must compare that.
    const quoting = '<NarrativeMemory version="0" source="nmos">\n  <Canon>write [NMOS.memory] here</Canon>\n</NarrativeMemory>';
    let now = 10_000;
    const { host, calls } = fakeHost((path, body) => {
      const res = happy(path, body);
      return path === '/v1/retrieve' ? { status: 200, json: { freshness: 'fresh', packet: { text: quoting } } } : res;
    });
    host.now = () => now;
    const adapter = createAdapter(host);
    const placedText = quoting.split(MEMORY_MARKER).join('');
    const count = (out: PromptMessage[]) => JSON.stringify(out).split('<NarrativeMemory version').length - 1;

    const userMarked: PromptMessage[] = [
      { role: 'system', content: 'narrator' },
      { role: 'user', content: `Where did we hide the lantern?\n${MEMORY_MARKER}` },
    ];
    const out1 = await adapter.beforeRequest(userMarked, 'model');
    expect(out1[1]?.content).toContain(placedText);
    expect(count(out1)).toBe(1);

    const out2 = await adapter.beforeRequest(out1, 'model');
    now += 200_000; // past the 120 s retry memo
    const out3 = await adapter.beforeRequest(out2, 'model');
    // Tier 1: the packet a placeholder put in the user block is seen by the retry guard (`hasPacket` with the chat),
    // so the third call no longer reaches recall (it did before, and only the holdsText fallback kept it single).
    expect(calls.filter((p) => p === '/v1/retrieve')).toHaveLength(1);
    expect(count(out2)).toBe(1);
    expect(count(out3)).toBe(1);
    expect(out3).toEqual(out1);
    expect(JSON.stringify(out3)).not.toContain(MEMORY_MARKER);
  });

  it('never mutates the host chat object on a successful request with a marker', async () => {
    const hostChat = structuredClone(chat);
    const snapshot = structuredClone(hostChat);
    const { host } = fakeHost(happy);
    host.currentChat = async () => hostChat;
    const input: PromptMessage[] = [
      { role: 'system', content: 'narrator' },
      { role: 'user', content: `Where did we hide the lantern?\n${MEMORY_MARKER}` },
    ];
    const out = await createAdapter(host).beforeRequest(input, 'model');
    expect(out[1]?.content).toContain(PACKET);
    expect(hostChat).toEqual(snapshot);
  });
});

describe('trimming old dialogue (PHASE-60 S1)', () => {
  /** `turns` replied turns (some short `응` / `…그래.` messages) and a long latest user message `u{turns}`. */
  function longChat(turns: number, trailing: HostMessage[] = []): HostChat {
    const message: HostMessage[] = [];
    for (let n = 0; n < turns; n += 1) {
      message.push({ role: 'user', chatId: `u${n}`, data: n % 5 === 0
        ? '응' : `세라 walked past lamp ${n} near the harbor archive and asked 카이토 about note ${n}.` });
      message.push({ role: 'char', chatId: `c${n}`, data: n % 7 === 0
        ? '…그래.' : `카이토 answered 세라 beside gate ${n} while 하나 recorded entry ${n} in the ledger.` });
    }
    message.push({ role: 'user', chatId: `u${turns}`,
      data: `유나 stepped onto the pier at turn ${turns} and asked 세라 where the bronze lantern went.` });
    message.push(...trailing);
    return { id: 'chat-long', message };
  }
  const PRESET = 'You are the narrator for 세라 and 카이토.';
  /** The host prompt: a system preset, then the whole chat one message each. */
  const promptOf = (c: HostChat): PromptMessage[] => [
    { role: 'system', content: PRESET },
    ...c.message!.map((m) => ({ role: (m.role === 'user' ? 'user' : 'assistant') as 'user' | 'assistant', content: m.data })),
  ];
  const noop: HttpResult = { status: 200, json: { status: 'noop', active_commit: 'c', manifest_hash: 'm', conversation_id: 'conv-1' } };
  /** The sidecar's rule with every turn covered: the first message of turn `cut` is the first one kept. */
  const cutOf = (turns: number, k: number) => Math.floor((turns - k) / k) * k;
  const quantized = (turns: number, extra: Record<string, unknown> = {}) => (body: any): HttpResult => {
    const k = body.trim?.keep_recent_turns;
    // A request without `trim` (Tier 1: the packet fetched again for a prompt that refused the boundary).
    if (!k) return { status: 200, json: { freshness: 'fresh', packet: { text: PACKET },
      coverage: { recorded_through_turn: turns - 1, covered_through_turn: turns - 1 }, ...extra } };
    const cut = cutOf(turns, k);
    return { status: 200, json: { freshness: 'fresh', packet: { text: PACKET },
      trim: cut > 0 ? { keep_from_id: `u${cut}`, keep_from_turn: cut, reason: null }
        : { keep_from_id: null, keep_from_turn: null, reason: 'short' },
      coverage: { recorded_through_turn: turns - 1, covered_through_turn: turns - 1 }, ...extra } };
  };

  /** A host whose chat is one held object (checked deep-equal after every call), trimming on with 4 recent turns. */
  function trimHost(held: HostChat, answer: (body: any) => HttpResult | Promise<HttpResult>,
                    overrides: Partial<Settings> = {}) {
    const bodies: any[] = [];
    const { host, calls } = fakeHost((path, body) => {
      if (path === '/v1/sync/reconcile') return noop;
      if (path === '/v1/retrieve') {
        bodies.push(body);
        return answer(body);
      }
      return { status: 404, json: null };
    }, { trimOldTurns: true, keepRecentTurns: 4, deadlineMs: 5000, ...overrides });
    const before = structuredClone(held);
    host.currentChat = async () => held;
    const events: ActivityEvent[] = [];
    const adapter = createAdapter(host, (e) => events.push(e));
    const run = async (p: PromptMessage[]) => {
      const out = await adapter.beforeRequest(p, 'model');
      expect(held).toEqual(before); // the host chat object is never written
      return out;
    };
    const last = async () => (await adapter.status()).last;
    const retrieves = () => calls.filter((c) => c === '/v1/retrieve').length;
    return { host, adapter, run, last, bodies, events, retrieves };
  }
  /** `p` with the packet as a system message right before its latest user message. */
  const withPacket = (p: PromptMessage[], text = PACKET): PromptMessage[] =>
    [...p.slice(0, -1), { role: 'system', content: text }, p[p.length - 1]!];

  it('A14: off sends no trim and returns the input plus the packet, as before', async () => {
    const held = structuredClone(chat);
    const snapshot = structuredClone(held);
    const bodies: any[] = [];
    const { host } = fakeHost((path, body) => {
      if (path === '/v1/retrieve') bodies.push(body);
      return happy(path, body);
    });
    host.currentChat = async () => held;
    const events: ActivityEvent[] = [];
    const adapter = createAdapter(host, (e) => events.push(e));
    const out = await adapter.beforeRequest(prompt, 'model');
    expect(out).toEqual([
      { role: 'system', content: 'narrator' },
      { role: 'system', content: PACKET },
      { role: 'user', content: 'Where did we hide the lantern?' },
    ]);
    expect('trim' in bodies[0]).toBe(false);
    const last = (await adapter.status()).last!;
    expect('trim' in last).toBe(false);
    expect(events.some((e) => 'trim' in e)).toBe(false);
    expect(held).toEqual(snapshot);
  });

  // Tier 1: `trim` is asked for only when the prompt holds dialogue a cut could drop, so these two tests send the
  // chat's earlier messages too (the default prompt holds only the latest user turn).
  const historyPrompt: PromptMessage[] = [
    { role: 'system', content: 'narrator' },
    { role: 'user', content: 'The lantern is hidden in the old archive.' },
    { role: 'assistant', content: 'Noted.' },
    { role: 'user', content: 'Where did we hide the lantern?' },
  ];
  const historyRecall = (bodies: any[]) => (path: string, body: any): HttpResult => {
    if (path !== '/v1/retrieve') return happy(path, body);
    bodies.push(body);
    return { status: 200, json: { freshness: 'fresh', packet: { text: PACKET } } };
  };

  it('A14: on, with an answer that has no trim (an older sidecar), drops nothing and says unsupported', async () => {
    const held = structuredClone(chat);
    const snapshot = structuredClone(held);
    const bodies: any[] = [];
    const { host } = fakeHost(historyRecall(bodies), { trimOldTurns: true, keepRecentTurns: 7 });
    host.currentChat = async () => held;
    const events: ActivityEvent[] = [];
    const adapter = createAdapter(host, (e) => events.push(e));
    const out = await adapter.beforeRequest(historyPrompt, 'model');
    expect(out).toEqual(withPacket(historyPrompt));
    expect(bodies[0].trim).toEqual({ keep_recent_turns: 7, step: 7 });
    expect((await adapter.status()).last?.trim).toEqual({ dropped: 0, savedTokens: 0, reason: 'unsupported',
      keepFromTurn: null });
    expect(events[1]).toMatchObject({ type: 'request-end', trim: { dropped: 0, savedTokens: 0, reason: 'unsupported' } });
    expect(held).toEqual(snapshot);
  });

  it('keeps keepRecentTurns within 4..200 in the request, and a missing one is 16', async () => {
    for (const [value, expected] of [[2, 4], [999, 200], [undefined, 16], [Number.NaN, 16]] as const) {
      const bodies: any[] = [];
      const { host } = fakeHost(historyRecall(bodies), { trimOldTurns: true, keepRecentTurns: value });
      await createAdapter(host).beforeRequest(structuredClone(historyPrompt), 'model');
      expect(bodies[0].trim, String(value)).toEqual({ keep_recent_turns: expected, step: expected });
    }
  });

  it('A15: drops exactly the messages before the boundary and places the packet before the latest user turn', async () => {
    const turns = 30;
    const held = longChat(turns);
    const h = trimHost(held, quantized(turns));
    const input = promptOf(held);
    const out = await h.run(input);
    const cut = cutOf(turns, 4);
    expect(cut).toBe(24);
    const kept = input.slice(1 + 2 * cut);
    expect(out).toEqual([input[0], ...withPacket(kept)]);
    expect(h.bodies[0].trim).toEqual({ keep_recent_turns: 4, step: 4 });
    const last = (await h.last())!;
    expect(last.trim).toEqual({ dropped: 2 * cut, savedTokens: expect.any(Number), reason: null, keepFromTurn: cut });
    expect(last.trim!.savedTokens).toBeGreaterThan(0);
    expect(last.coverage).toEqual({ recordedThroughTurn: turns - 1, coveredThroughTurn: turns - 1 });
    expect(h.events[1]).toMatchObject({ type: 'request-end', outcome: 'injected',
      trim: { dropped: 2 * cut, savedTokens: last.trim!.savedTokens, reason: null } });
  });

  it('A15: over a growing chat the kept prefix stays the same until the boundary moves by a whole step', async () => {
    const k = 4;
    const firstTwo = new Map<number, PromptMessage[]>();
    let previousCut = -1;
    for (let turns = 29; turns <= 29 + 2 * k; turns += 1) {
      const held = longChat(turns);
      const h = trimHost(held, quantized(turns), { keepRecentTurns: k });
      const out = await h.run(promptOf(held));
      const cut = cutOf(turns, k);
      expect(cut % k).toBe(0);
      expect((await h.last())?.trim).toMatchObject({ dropped: 2 * cut, reason: null, keepFromTurn: cut });
      const head = out.slice(0, 2);
      if (firstTwo.has(cut)) expect(head, `turns ${turns}`).toEqual(firstTwo.get(cut));
      else firstTwo.set(cut, head);
      if (previousCut >= 0 && cut !== previousCut) {
        expect(cut - previousCut).toBe(k);
        expect(head).not.toEqual(firstTwo.get(previousCut));
      }
      previousCut = cut;
    }
    expect(firstTwo.size).toBeGreaterThanOrEqual(2);
  });

  it('a boundary at the latest user message drops only the messages before it', async () => {
    const turns = 12;
    const held = longChat(turns);
    const h = trimHost(held, () => ({ status: 200, json: { freshness: 'fresh', packet: { text: PACKET },
      trim: { keep_from_id: `u${turns}`, keep_from_turn: turns, reason: null } } }));
    const input = promptOf(held);
    const out = await h.run(input);
    expect(out).toEqual([input[0], { role: 'system', content: PACKET }, input[input.length - 1]]);
    expect((await h.last())?.trim).toMatchObject({ dropped: 2 * turns, reason: null, keepFromTurn: turns });
  });

  it('a boundary after the latest user message, an unknown one or a merged-chat preset drops nothing (format)', async () => {
    const turns = 12;
    const answerWith = (id: string) => () => ({ status: 200, json: { freshness: 'fresh', packet: { text: PACKET },
      trim: { keep_from_id: id, keep_from_turn: 9, reason: null } } });
    // After it: a reply the host already holds after the latest user message, sent as a prefill.
    const after = longChat(turns, [{ role: 'char', chatId: 'c-after', data: '세라 turned toward the harbor without a word.' }]);
    const afterPrompt = promptOf(after);
    const a = trimHost(after, answerWith('c-after'));
    expect(await a.run(afterPrompt)).toEqual([...withPacket(afterPrompt.slice(0, -1)), afterPrompt[afterPrompt.length - 1]]);
    expect((await a.last())?.trim).toEqual({ dropped: 0, savedTokens: 0, reason: 'format', keepFromTurn: null });

    const held = longChat(turns);
    const input = promptOf(held);
    const u = trimHost(held, answerWith('no-such-id'));
    expect(await u.run(input)).toEqual(withPacket(input));
    expect((await u.last())?.trim).toMatchObject({ dropped: 0, reason: 'format' });

    const merged: PromptMessage[] = [{ role: 'system', content: PRESET },
      { role: 'user', content: held.message!.map((m) => m.data).join('\n') }];
    const m = trimHost(held, answerWith('u8'));
    expect(await m.run(merged)).toEqual(withPacket(merged));
    expect((await m.last())?.trim).toMatchObject({ dropped: 0, reason: 'format' });
    expect(m.events[1]).toMatchObject({ trim: { dropped: 0, savedTokens: 0, reason: 'format' } });
  });

  it('a stale answer, a failed or throwing retrieve and an empty packet drop nothing', async () => {
    const turns = 30;
    const held = longChat(turns);
    const input = promptOf(held);

    const stale = trimHost(held, (body) => ({ ...quantized(turns)(body),
      json: { ...(quantized(turns)(body).json as object), freshness: 'stale' } }));
    expect(await stale.run(input)).toEqual(input);
    expect((await stale.last())?.trim).toEqual({ dropped: 0, savedTokens: 0, reason: 'failed', keepFromTurn: null });

    const down = trimHost(held, () => ({ status: 500, json: null }));
    expect(await down.run(input)).toEqual(input);
    expect((await down.last())).toMatchObject({ outcome: 'failed',
      trim: { dropped: 0, savedTokens: 0, reason: 'failed', keepFromTurn: null } });
    expect(down.events[1]).toMatchObject({ outcome: 'failed', trim: { dropped: 0, savedTokens: 0, reason: 'failed' } });
    // The miss is cached briefly: a retry is still failed, nothing dropped.
    expect(await down.run(structuredClone(input))).toEqual(input);
    expect(down.retrieves()).toBe(1);
    expect(down.events[3]).toMatchObject({ trim: { dropped: 0, reason: 'failed' } });

    const throws = trimHost(held, () => Promise.reject(new TypeError('Failed to fetch')));
    expect(await throws.run(input)).toEqual(input);
    expect((await throws.last())?.trim).toMatchObject({ dropped: 0, reason: 'failed' });

    const empty = trimHost(held, (body) => ({ status: 200, json: { ...(quantized(turns)(body).json as object),
      packet: { text: '' } } }));
    expect(await empty.run(input)).toEqual(input);
    expect((await empty.last())?.trim).toEqual({ dropped: 0, savedTokens: 0, reason: 'empty_packet', keepFromTurn: null });
  });

  it('shows a reason the sidecar gives without a boundary, and treats an answer with neither as failed', async () => {
    const held = longChat(30);
    const input = promptOf(held);
    const short = trimHost(held, () => ({ status: 200, json: { freshness: 'fresh', packet: { text: PACKET },
      trim: { keep_from_id: null, keep_from_turn: null, reason: 'no_summaries' } } }));
    expect(await short.run(input)).toEqual(withPacket(input));
    expect((await short.last())?.trim).toEqual({ dropped: 0, savedTokens: 0, reason: 'no_summaries', keepFromTurn: null });
    const odd = trimHost(held, () => ({ status: 200, json: { freshness: 'fresh', packet: { text: PACKET },
      trim: { keep_from_id: '', keep_from_turn: 'x', reason: 7 } } }));
    expect(await odd.run(input)).toEqual(withPacket(input));
    expect((await odd.last())?.trim).toEqual({ dropped: 0, savedTokens: 0, reason: 'failed', keepFromTurn: null });
  });

  it('a cached packet applies the same boundary to the same host prompt without a second retrieve', async () => {
    const turns = 30;
    const held = longChat(turns);
    const h = trimHost(held, quantized(turns));
    const first = await h.run(promptOf(held));
    const firstTrim = (await h.last())?.trim;
    const again = await h.run(promptOf(held));
    expect(again).toEqual(first);
    expect(h.retrieves()).toBe(1);
    expect((await h.last())?.trim).toEqual(firstTrim);
    expect((await h.last())?.coverage).toEqual({ recordedThroughTurn: turns - 1, coveredThroughTurn: turns - 1 });
    expect(h.events[3]).toMatchObject({ reused: true, trim: { dropped: 2 * 24, reason: null } });
  });

  it('H2: three chained calls give identical prompts with one retrieve, with and without a marker', async () => {
    const turns = 30;
    for (const marked of [true, false]) {
      const held = longChat(turns);
      let counter = 0;
      const h = trimHost(held, (body) => {
        counter += 1;
        const res = quantized(turns)(body);
        return { ...res, json: { ...(res.json as object), packet: { text:
          `<NarrativeMemory version="0" source="nmos">\n  <Excerpt turn="0" speaker="user">lantern #${counter}</Excerpt>\n</NarrativeMemory>` } } };
      });
      const input = promptOf(held);
      if (marked) {
        const latest = input[input.length - 1]!;
        input[input.length - 1] = { ...latest, content: `${latest.content as string}\n${MEMORY_MARKER}` };
      }
      const out1 = await h.run(input);
      expect(out1.length, String(marked)).toBeLessThan(input.length - 40);
      const out2 = await h.run(out1);
      const out3 = await h.run(out2);
      expect(out2, String(marked)).toBe(out1);
      expect(out3, String(marked)).toBe(out2);
      expect(out3, String(marked)).toEqual(out1);
      expect(h.retrieves(), String(marked)).toBe(1);
    }
  });

  it('a marker inside a message the boundary would drop: nothing dropped (format), the packet at the marker', async () => {
    const turns = 30;
    const held = longChat(turns);
    const h = trimHost(held, quantized(turns));
    const input = promptOf(held);
    const index = 1 + 2 * 3 + 1; // c3, well before the boundary at turn 24
    input[index] = { ...input[index]!, content: `${input[index]!.content as string}\n${MEMORY_MARKER}` };
    const out = await h.run(input);
    expect(out).toHaveLength(input.length);
    expect(out[index]?.content).toBe(`${held.message![2 * 3 + 1]!.data}\n${PACKET}`);
    expect((await h.last())?.trim).toEqual({ dropped: 0, savedTokens: 0, reason: 'format', keepFromTurn: null });
  });
});
