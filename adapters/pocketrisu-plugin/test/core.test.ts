import { describe, expect, it, vi } from 'vitest';
import { createAdapter, type HostPort, type HttpResult, type Settings } from '../src/core';
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
      deadlineMs: 200, injectPosition: 'before_last_user', ...overrides }),
    currentChat: async () => structuredClone(chat),
    post: async (url, body) => {
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

describe('beforeRequest', () => {
  it('reconciles, uploads bodies, retrieves once and injects', async () => {
    const { host, calls } = fakeHost(happy);
    const out = await createAdapter(host).beforeRequest(prompt, 'model');
    expect(calls).toEqual(['/v1/sync/reconcile', '/v1/sync/bodies', '/v1/retrieve']);
    expect(hasPacket(out)).toBe(true);
    expect(out[1]?.role).toBe('system');
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
  });

  it('gives up at the deadline and returns the prompt unchanged', async () => {
    const { host, warn } = fakeHost(() => new Promise<HttpResult>(() => {}), { deadlineMs: 50 });
    const started = performance.now();
    expect(await createAdapter(host).beforeRequest(prompt, 'model')).toBe(prompt);
    expect(performance.now() - started).toBeLessThan(300);
    expect(String(warn.mock.calls[0]?.[1])).toContain('deadline');
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
