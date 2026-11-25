// Tier 4, plugin side: the background sync after a reply (G6) and recall's query on a Continue (G7).

import { describe, expect, it, vi } from 'vitest';
import { CONFIG_REFRESH_MS, createAdapter, memoryMark, OUTPUT_SYNC_MS, outputSwitchOf, type AdapterOptions, type HostPort, type HttpResult,
  type Settings } from '../src/core';
import { BURST_MESSAGES, CONTINUE_QUERY_TAIL, hasPacket, queryTexts } from '../src/prompt';
import type { HostChat, HostMessage, PromptMessage } from '../src/types';

const PACKET = '<NarrativeMemory version="0" source="nmos">\n  <Excerpt turn="0" speaker="user">lantern</Excerpt>\n</NarrativeMemory>';
const REPLY = 'Sera lifts the lantern from the archive shelf and turns toward the harbor, where the bell keeps ringing.';

const baseChat: HostChat = {
  id: 'chat-1',
  message: [
    { role: 'user', data: 'The lantern is hidden in the old archive.', chatId: 'u0' },
    { role: 'char', data: 'Noted.', chatId: 'c0', generationInfo: { generationId: 'c0' } },
    { role: 'user', data: 'Where did we hide the lantern?', chatId: 'u1' },
  ],
};
const replied: HostChat = { ...baseChat, message: [...baseChat.message!,
  { role: 'char', data: REPLY, chatId: 'c1', generationInfo: { generationId: 'c1' } }] };
const prompt: PromptMessage[] = [
  { role: 'system', content: 'narrator' },
  { role: 'user', content: 'Where did we hide the lantern?' },
];

/** What `GET /v1/config` answers for the switch: a boolean, not reported (an older sidecar), or a failed read. */
type SwitchAnswer = boolean | 'absent' | 'fail';

/** A sidecar that answers every sync at once, and timers the test runs by hand. `config`: its switch
 *  `extraction.on_output` (PHASE-67), on unless a test says otherwise. */
function harness(overrides: Partial<Settings> = {}, handler?: (path: string, body: any) => Promise<HttpResult> | HttpResult,
  config: SwitchAnswer = true) {
  const calls: { path: string; body: any }[] = [];
  const timers: { run: () => void; ms: number; cleared: boolean }[] = [];
  const refreshTimers: { run: () => void; ms: number }[] = [];
  let switchAnswer: SwitchAnswer = config;
  const configAnswer = (): HttpResult => (switchAnswer === 'fail' ? { status: 503, json: { detail: 'down' } }
    : { status: 200, json: { extraction: { backfill: 0, ...(switchAnswer === 'absent' ? {} : { on_output: switchAnswer }) } } });
  const debug = vi.fn();
  let current: HostChat | null = structuredClone(replied);
  const answer = (path: string, body: any): HttpResult => {
    if (path === '/v1/sync/reconcile') return { status: 200, json: { conversation_id: 'conv-1', status: 'needs_bodies',
      active_commit: null, manifest_hash: 'm',
      needed_bodies: body.messages.map((m: any) => ({ host_logical_id: m.host_logical_id, revision_hash: m.revision_hash })) } };
    if (path === '/v1/sync/bodies') return { status: 200, json: { ok: true,
      reconcile: { conversation_id: 'conv-1', status: 'applied', active_commit: 'commit-1', manifest_hash: 'm' } } };
    if (path === '/v1/retrieve') return { status: 200, json: { freshness: 'fresh', packet: { text: PACKET } } };
    if (path === '/v1/output') return { status: 202, json: {} };
    return { status: 404, json: null };
  };
  const host: HostPort = {
    settings: async () => ({ sidecarUrl: 'http://sidecar', authToken: 't', enabled: true, reservedMemoryTokens: 600,
      deadlineMs: 2000, injectPosition: 'before_last_user', route: 'direct', language: 'en', ...overrides }),
    currentChat: async () => structuredClone(current),
    request: async (_method, url, body) => {
      const path = url.replace('http://sidecar', '');
      calls.push({ path, body });
      if (path === '/v1/config') return configAnswer();
      return handler ? handler(path, body) : answer(path, body);
    },
    warn: () => {},
    debug,
    now: () => performance.now(),
  };
  const options = {
    setTimer: (run: () => void, ms: number) => { const t = { run, ms, cleared: false }; timers.push(t); return t; },
    clearTimer: (handle: unknown) => { (handle as { cleared: boolean }).cleared = true; },
    setRefreshTimer: (run: () => void, ms: number) => { const t = { run, ms }; refreshTimers.push(t); return t; },
  };
  const pending = () => timers.filter((t) => !t.cleared);
  const fire = async () => {
    for (const t of pending()) { t.cleared = true; t.run(); }
    await settle();
  };
  /** The adapter as `entry.ts` starts it: the switch read at load; that read is left out of `calls`. */
  const start = async (extra: AdapterOptions = {}) => {
    const adapter = createAdapter(host, undefined, { ...options, ...extra });
    adapter.warmConfig();
    await settle();
    calls.length = 0;
    return adapter;
  };
  return { host, calls, timers, refreshTimers, pending, fire, debug, options, start, answer,
    setSwitch: (a: SwitchAnswer) => { switchAnswer = a; },
    setChat: (c: HostChat | null) => { current = c; }, paths: () => calls.map((c) => c.path) };
}

const settle = async () => { for (let i = 0; i < 20; i += 1) await new Promise((resolve) => setTimeout(resolve, 0)); };

describe('background sync after a reply (G6)', () => {
  it('syncs the chat as it is once the wait is over, marked as after a reply, and nothing more', async () => {
    const h = harness();
    const adapter = await h.start();
    adapter.onOutput({ chat: structuredClone(replied), messageIndex: 3 });
    await settle();
    expect(h.paths()).toEqual(['/v1/output']);  // the notification at once; the sync waits
    expect(h.pending().map((t) => t.ms)).toEqual([OUTPUT_SYNC_MS]);
    expect(OUTPUT_SYNC_MS).toBe(20_000);
    await h.fire();
    expect(h.paths()).toEqual(['/v1/output', '/v1/sync/reconcile', '/v1/sync/bodies']);
    const reconcile = h.calls[1]!.body;
    expect(reconcile.trigger).toBe('output');
    expect(reconcile.chat_id).toBe('chat-1');
    expect(reconcile.messages.map((m: any) => m.host_logical_id)).toEqual(['u0', 'c0', 'u1', 'c1']);  // the reply too
    expect(h.calls[2]!.body.then_reconcile.trigger).toBe('output');
    expect(h.paths().filter((p) => p === '/v1/retrieve')).toEqual([]);  // no recall, no model call
  });

  it('reads the chat when the wait is over, not the output snapshot (H7)', async () => {
    const h = harness();
    const adapter = await h.start();
    const later = structuredClone(replied);
    later.message![3]!.data = `${REPLY} (rewritten by a trigger)`;
    adapter.onOutput({ chat: structuredClone(replied), messageIndex: 3 });
    await settle();
    h.setChat(later);
    await h.fire();
    const bodies = h.calls.find((c) => c.path === '/v1/sync/bodies')!.body.bodies;
    expect(bodies.find((b: any) => b.host_logical_id === 'c1').content).toContain('rewritten by a trigger');
  });

  it('waits again after each reply: one sync for replies in a row', async () => {
    const h = harness();
    const adapter = await h.start();
    adapter.onOutput({ chat: structuredClone(replied), messageIndex: 3 });
    await settle();
    adapter.onOutput({ chat: structuredClone(replied), messageIndex: 3 });
    await settle();
    expect(h.timers).toHaveLength(2);
    expect(h.pending()).toHaveLength(1);
    await h.fire();
    expect(h.paths().filter((p) => p === '/v1/sync/reconcile')).toHaveLength(1);
  });

  it('is cancelled by a main request (a reroll, a quick reply), but not by an auxiliary one (Auto Suggest)', async () => {
    const h = harness();
    const adapter = await h.start();
    adapter.onOutput({ chat: structuredClone(replied), messageIndex: 3 });
    await settle();
    await adapter.beforeRequest([{ role: 'user', content: 'suggest something' }], 'submodel');
    expect(h.pending()).toHaveLength(1);  // Auto Suggest runs after every reply: it leaves the sync waiting
    h.setChat(structuredClone(baseChat));  // a reroll removes the tail reply before its request (H14)
    await adapter.beforeRequest(structuredClone(prompt), 'model');
    expect(h.pending()).toHaveLength(0);
    const before = h.calls.length;
    await h.fire();
    expect(h.calls.length).toBe(before);
  });

  it("an auxiliary call in `model` mode (a script's own model call) leaves it; the chat's own request clears it", async () => {
    const h = harness();
    const adapter = await h.start();
    adapter.onOutput({ chat: structuredClone(replied), messageIndex: 3 });
    await settle();
    await adapter.beforeRequest([{ role: 'user', content: 'Summarize the weather in one line.' }], 'model');
    expect(h.pending()).toHaveLength(1);  // no turn of the chat in it: the sync still waits (review finding 6)
    await h.fire();
    expect(h.paths().filter((p) => p === '/v1/sync/reconcile')).toHaveLength(1);
    adapter.onOutput({ chat: structuredClone(replied), messageIndex: 3 });
    await settle();
    h.setChat(structuredClone(baseChat));
    await adapter.beforeRequest(structuredClone(prompt), 'model');
    expect(h.pending()).toHaveLength(0);
  });

  it('a sync a main request overtook stops before its next step', async () => {
    let release!: () => void;
    const gate = new Promise<void>((r) => { release = r; });
    const h = harness({}, async (path, body) => {
      if (path === '/v1/sync/reconcile' && body.trigger === 'output') {
        await gate;
        return { status: 200, json: { conversation_id: 'conv-1', status: 'needs_bodies', active_commit: null,
          manifest_hash: 'm', needed_bodies: [{ host_logical_id: 'c1', revision_hash: body.messages[3].revision_hash }] } };
      }
      if (path === '/v1/sync/reconcile') return { status: 200, json: { conversation_id: 'conv-1', status: 'noop',
        active_commit: 'commit-1', manifest_hash: 'm' } };
      if (path === '/v1/retrieve') return { status: 200, json: { freshness: 'fresh', packet: { text: PACKET } } };
      return { status: 202, json: {} };
    });
    const adapter = await h.start();
    adapter.onOutput({ chat: structuredClone(replied), messageIndex: 3 });
    await settle();
    await h.fire();  // the background reconcile is on its way
    h.setChat(structuredClone(baseChat));  // a reroll
    const out = adapter.beforeRequest(structuredClone(prompt), 'model');
    await settle();
    // The request waits for the background sync before its own, so its own applies last.
    expect(h.calls.filter((c) => c.path === '/v1/sync/reconcile').map((c) => c.body.trigger ?? null)).toEqual(['output']);
    release();
    expect(hasPacket(await out)).toBe(true);
    expect(h.calls.filter((c) => c.path === '/v1/sync/reconcile').map((c) => c.body.trigger ?? null)).toEqual(['output', null]);
    expect(h.paths().filter((p) => p === '/v1/sync/bodies')).toEqual([]);  // the overtaken sync stopped
    expect(h.debug.mock.calls.some((c) => /background sync after the reply failed/.test(String(c[0]))
      && /newer request or reply/.test(String(c[1])))).toBe(true);
  });

  it('does nothing once another chat is open', async () => {
    const h = harness();
    const adapter = await h.start();
    adapter.onOutput({ chat: structuredClone(replied), messageIndex: 3 });
    await settle();
    h.setChat({ ...structuredClone(replied), id: 'chat-2' });
    await h.fire();
    expect(h.paths()).toEqual(['/v1/output']);
  });

  it('is not scheduled when NMOS is off, off for the chat, or the wait is 0', async () => {
    for (const [overrides, ms] of [[{ enabled: false }, undefined], [{ offChats: ['chat-1'] }, undefined], [{}, 0]] as const) {
      const h = harness(overrides);
      const adapter = await h.start(ms === undefined ? {} : { outputSyncMs: ms });
      adapter.onOutput({ chat: structuredClone(replied), messageIndex: 3 });
      await settle();
      await h.fire();
      expect(h.paths().filter((p) => p.startsWith('/v1/sync'))).toEqual([]);
    }
  });

  it('a request waits at most a moment for a background sync that does not answer', async () => {
    const h = harness({ deadlineMs: 600 }, (path, body) => (path === '/v1/sync/reconcile' && body.trigger === 'output'
      ? new Promise<HttpResult>(() => {})
      : path === '/v1/sync/reconcile' ? { status: 200, json: { conversation_id: 'conv-1', status: 'noop',
        active_commit: 'commit-1', manifest_hash: 'm' } }
        : path === '/v1/retrieve' ? { status: 200, json: { freshness: 'fresh', packet: { text: PACKET } } }
          : { status: 202, json: {} }));
    const adapter = await h.start();
    adapter.onOutput({ chat: structuredClone(replied), messageIndex: 3 });
    await settle();
    await h.fire();
    h.setChat(structuredClone(baseChat));
    expect(hasPacket(await adapter.beforeRequest(structuredClone(prompt), 'model'))).toBe(true);  // within its deadline
  });

  it('fails open: an unreachable sidecar neither throws nor stops the next request', async () => {
    const h = harness({}, () => { throw new Error('TypeError: Failed to fetch'); });
    const adapter = await h.start();
    expect(() => adapter.onOutput({ chat: structuredClone(replied), messageIndex: 3 })).not.toThrow();
    await settle();
    expect(h.pending()).toHaveLength(1);  // scheduled even though the notification failed
    await h.fire();
    expect(h.paths()).toEqual(['/v1/output', '/v1/sync/reconcile']);
    expect(h.debug.mock.calls.some((c) => /background sync after the reply failed/.test(String(c[0])))).toBe(true);
    expect(await adapter.beforeRequest(structuredClone(prompt), 'model')).toEqual(prompt);
  });

  it("drops the chat's cached packets once it ran, so a reroll syncs again instead of reusing one", async () => {
    const h = harness();
    const adapter = await h.start();
    h.setChat(structuredClone(baseChat));
    await adapter.beforeRequest(structuredClone(prompt), 'model');
    await adapter.beforeRequest(structuredClone(prompt), 'model');  // the same state: served from the cache
    expect(h.paths().filter((p) => p === '/v1/retrieve')).toHaveLength(1);
    h.setChat(structuredClone(replied));
    adapter.onOutput({ chat: structuredClone(replied), messageIndex: 3 });
    await settle();
    await h.fire();
    h.setChat(structuredClone(baseChat));  // reroll: the tail reply is gone before the request (H14)
    const reconciles = h.paths().filter((p) => p === '/v1/sync/reconcile').length;
    expect(hasPacket(await adapter.beforeRequest(structuredClone(prompt), 'model'))).toBe(true);
    expect(h.paths().filter((p) => p === '/v1/sync/reconcile').length).toBe(reconciles + 1);
    expect(h.paths().filter((p) => p === '/v1/retrieve')).toHaveLength(2);
  });
});

describe('the background sync sends only the chat replied in (review finding 4)', () => {
  it('a chat still loading (0 messages) after a switch away and back: no sync; the next request syncs as always', async () => {
    const h = harness();
    const adapter = await h.start();
    adapter.onOutput({ chat: structuredClone(replied), messageIndex: 3 });
    await settle();
    h.setChat({ id: 'chat-2', message: [] });  // switched away
    h.setChat({ id: 'chat-1', message: [] });  // and back: the content is not loaded yet (HOST-FACTS Q8 item 7)
    await h.fire();
    expect(h.paths()).toEqual(['/v1/output']);  // no reconcile: an empty manifest would retract the head
    expect(h.debug.mock.calls.some((c) => /background sync skipped/.test(String(c[0])))).toBe(true);
    h.setChat(structuredClone(replied));
    await adapter.beforeRequest(structuredClone(prompt), 'model');
    expect(h.paths().filter((p) => p === '/v1/sync/reconcile')).toHaveLength(1);
  });

  it('with the reply in the chat read: one sync', async () => {
    const h = harness();
    const adapter = await h.start();
    adapter.onOutput({ chat: structuredClone(replied), messageIndex: 3 });
    await settle();
    h.setChat({ id: 'chat-2', message: [] });
    h.setChat(structuredClone(replied));  // back, loaded
    await h.fire();
    expect(h.paths().filter((p) => p === '/v1/sync/reconcile')).toHaveLength(1);
  });

  it('a snapshot that holds the reply but is shorter than the plugin last synced is not sent', async () => {
    const h = harness();
    const adapter = await h.start();
    const longer: HostChat = { ...structuredClone(replied), message: [...structuredClone(replied).message!,
      { role: 'user', data: 'And then?', chatId: 'u2' }] };
    h.setChat(longer);
    await adapter.beforeRequest([{ role: 'system', content: 'narrator' }, { role: 'user', content: 'And then?' }], 'model');
    expect(h.paths().filter((p) => p === '/v1/sync/reconcile')).toHaveLength(1);  // 5 messages synced
    adapter.onOutput({ chat: structuredClone(replied), messageIndex: 3 });
    await settle();
    h.setChat(structuredClone(replied));  // 4 messages: a partial read
    const before = h.calls.length;
    await h.fire();
    expect(h.calls.slice(before).map((c) => c.path)).toEqual([]);
  });

  it('a reply whose id is not known is never scheduled', async () => {
    const h = harness();
    const adapter = await h.start();
    adapter.onOutput({ chat: structuredClone(replied) });  // no message index
    await settle();
    expect(h.pending()).toHaveLength(0);
  });
});

describe("the background sync only while the sidecar extracts a reply right after it (extraction.on_output)", () => {
  /** What a request sends, without its timings (they differ from run to run). */
  const sent = (calls: { path: string; body: any }[]) => calls.map((c) => {
    if (!c.body || typeof c.body !== 'object') return [c.path, c.body ?? null];
    const { client_timings_ms: _t, ...rest } = c.body;
    return [c.path, rest];
  });

  it('reads the switch at load and again every few minutes, never on a request or a reply', async () => {
    const h = harness();
    const adapter = createAdapter(h.host, undefined, h.options);
    adapter.warmConfig();
    adapter.warmConfig();  // once per page
    await settle();
    expect(h.paths()).toEqual(['/v1/config']);
    expect(h.refreshTimers.map((t) => t.ms)).toEqual([CONFIG_REFRESH_MS]);
    expect(CONFIG_REFRESH_MS).toBe(300_000);
    h.calls.length = 0;
    h.setChat(structuredClone(baseChat));
    await adapter.beforeRequest(structuredClone(prompt), 'model');
    h.setChat(structuredClone(replied));
    adapter.onOutput({ chat: structuredClone(replied), messageIndex: 3 });
    await settle();
    expect(h.paths()).not.toContain('/v1/config');
    h.refreshTimers[0]!.run();
    await settle();
    expect(h.paths().filter((p) => p === '/v1/config')).toHaveLength(1);
    expect(h.refreshTimers).toHaveLength(2);  // and the next one
  });

  for (const [label, answer] of [['off', false], ['not reported (an older sidecar)', 'absent'],
    ['unknown (the read failed)', 'fail'], ['not read yet', null]] as const) {
    it(`schedules nothing and waits for nothing when the switch is ${label}`, async () => {
      const h = harness({}, undefined, answer ?? true);
      const adapter = answer === null ? createAdapter(h.host, undefined, h.options) : await h.start();
      adapter.onOutput({ chat: structuredClone(replied), messageIndex: 3 });
      await settle();
      expect(h.timers).toHaveLength(0);  // no timer at all
      expect(h.paths()).toEqual(['/v1/output']);
      h.setChat(structuredClone(baseChat));  // a reroll
      expect(hasPacket(await adapter.beforeRequest(structuredClone(prompt), 'model'))).toBe(true);
      // The calls are those of a build without the background sync.
      const without = harness({}, undefined, answer ?? true);
      const plain = createAdapter(without.host, undefined, { ...without.options, outputSyncMs: 0 });
      plain.onOutput({ chat: structuredClone(replied), messageIndex: 3 });
      await settle();
      without.setChat(structuredClone(baseChat));
      await plain.beforeRequest(structuredClone(prompt), 'model');
      expect(sent(h.calls)).toEqual(sent(without.calls));
      expect(h.paths()).toEqual(['/v1/output', '/v1/sync/reconcile', '/v1/sync/bodies', '/v1/retrieve']);
      expect(h.calls.some((c) => c.body?.trigger !== undefined)).toBe(false);
    });
  }

  it("follows the panel: a save that turns it off stops a waiting sync, a read that reports it on starts the next", async () => {
    const h = harness();
    const adapter = await h.start();
    adapter.onOutput({ chat: structuredClone(replied), messageIndex: 3 });
    await settle();
    expect(h.pending()).toHaveLength(1);
    h.setSwitch(false);
    await adapter.api('PUT', '/v1/config', { extract_on_output: false });
    await h.fire();
    expect(h.paths().filter((p) => p.startsWith('/v1/sync'))).toEqual([]);  // checked again when the wait was over
    h.setSwitch(true);
    await adapter.api('GET', '/v1/config');
    adapter.onOutput({ chat: structuredClone(replied), messageIndex: 3 });
    await settle();
    await h.fire();
    expect(h.paths().filter((p) => p === '/v1/sync/reconcile')).toHaveLength(1);
  });

  it('a failed panel read or save makes it unknown, so off', async () => {
    const h = harness();
    const adapter = await h.start();
    h.setSwitch('fail');
    await expect(adapter.api('PUT', '/v1/config', { extract_on_output: true })).rejects.toThrow(/HTTP 503/);
    adapter.onOutput({ chat: structuredClone(replied), messageIndex: 3 });
    await settle();
    expect(h.timers).toHaveLength(0);
  });

  it('a read of another sidecar does not count for this one', async () => {
    let url = 'http://sidecar';
    const h = harness();
    const settings = h.host.settings;
    h.host.settings = async () => ({ ...(await settings()), sidecarUrl: url });
    const adapter = await h.start();
    url = 'http://sidecar/';  // the same one, written with a slash
    adapter.onOutput({ chat: structuredClone(replied), messageIndex: 3 });
    await settle();
    expect(h.pending()).toHaveLength(1);
    url = 'http://other-sidecar';
    adapter.onOutput({ chat: structuredClone(replied), messageIndex: 3 });
    await settle();
    expect(h.pending()).toHaveLength(0);
  });

  it('only a boolean true is on', () => {
    expect(outputSwitchOf({ extraction: { on_output: true } })).toBe(true);
    for (const c of [{ extraction: { on_output: false } }, { extraction: { on_output: 'true' } }, { extraction: {} }, {}, null, 1]) {
      expect(outputSwitchOf(c)).toBe(false);
    }
  });
});

describe('a cached packet is not reused once the memory moved (4.3.2)', () => {
  const cov = (compiled: number, extra: Record<string, unknown> = {}) => ({
    extraction: { generation: { key: 'x' }, eligible: 3, compiled, pending: 3 - compiled, failed: 0 },
    embeddings: { generation: { key: 'e' }, eligible: 4, embedded: 4, pending: 0, failed: 0 },
    produced: { facts: compiled * 2, summaries: 0 }, ...extra });
  /** The switch off (the default): the gap is the same whatever it says. */
  const setup = () => {
    let coverage: unknown = cov(1);
    const h = harness({}, (path, body) => (path.includes('/coverage') ? { status: 200, json: coverage } : h.answer(path, body)),
      false);
    h.setChat(structuredClone(baseChat));
    return { h, setCoverage: (c: unknown) => { coverage = c; } };
  };
  const retrieves = (h: ReturnType<typeof harness>) => h.paths().filter((p) => p === '/v1/retrieve').length;

  it('a coverage answer that says more is held drops the chat\'s packets; the same answer again does not', async () => {
    const { h, setCoverage } = setup();
    const adapter = await h.start();
    await adapter.beforeRequest(structuredClone(prompt), 'model');
    await adapter.beforeRequest(structuredClone(prompt), 'model');  // a reroll of the unchanged chat: from the cache
    expect(retrieves(h)).toBe(1);
    await adapter.api('GET', '/v1/conversations/conv-1/coverage', undefined, 5000);  // first seen: nothing to compare
    await adapter.beforeRequest(structuredClone(prompt), 'model');
    expect(retrieves(h)).toBe(2);
    await adapter.api('GET', '/v1/conversations/conv-1/coverage', undefined, 5000);  // the same: the packet stays
    await adapter.beforeRequest(structuredClone(prompt), 'model');
    expect(retrieves(h)).toBe(2);
    setCoverage(cov(2));  // an extraction finished
    await adapter.api('GET', '/v1/conversations/conv-1/coverage?usage=1', undefined, 5000);  // the panel's read counts too
    await adapter.beforeRequest(structuredClone(prompt), 'model');
    expect(retrieves(h)).toBe(3);
    setCoverage(cov(2, { canon: { generation: { key: 'c' }, wanted: 2, read: 1, pending: 1 } }));  // a canon text read
    await adapter.api('GET', '/v1/conversations/conv-1/coverage', undefined, 5000);
    await adapter.beforeRequest(structuredClone(prompt), 'model');
    expect(retrieves(h)).toBe(4);
  });

  it("another conversation's coverage, or an answer that says nothing of memory, leaves it", async () => {
    const { h, setCoverage } = setup();
    const adapter = await h.start();
    await adapter.beforeRequest(structuredClone(prompt), 'model');
    await adapter.api('GET', '/v1/conversations/conv-2/coverage', undefined, 5000);
    setCoverage({ extraction: { generation: null }, embeddings: { generation: null } });
    await adapter.api('GET', '/v1/conversations/conv-1/coverage', undefined, 5000);
    await adapter.api('GET', '/v1/conversations/conv-1/entities', undefined, 5000).catch(() => {});  // not coverage
    await adapter.beforeRequest(structuredClone(prompt), 'model');
    expect(retrieves(h)).toBe(1);
  });

  it('a request running when the memory moved does not remember its packet', async () => {
    let release!: () => void;
    const gate = new Promise<void>((r) => { release = r; });
    let coverage: unknown = cov(1);
    let held = false;
    const h = harness({ deadlineMs: 5000 }, async (path, body) => {
      if (path.includes('/coverage')) return { status: 200, json: coverage };
      if (path === '/v1/retrieve' && held) { held = false; await gate; }
      return h.answer(path, body);
    }, false);
    h.setChat(structuredClone(baseChat));
    const adapter = await h.start();
    await adapter.api('GET', '/v1/conversations/conv-1/coverage', undefined, 5000);  // seen before: a baseline
    await adapter.beforeRequest(structuredClone(prompt), 'model');  // knows conv-1 for chat-1 now
    await adapter.api('POST', '/v1/noop').catch(() => {});  // a panel change: nothing cached
    held = true;
    const running = adapter.beforeRequest(structuredClone(prompt), 'model');
    await settle();
    coverage = cov(2);
    await adapter.api('GET', '/v1/conversations/conv-1/coverage', undefined, 5000);  // while its recall runs
    release();
    expect(hasPacket(await running)).toBe(true);  // it still goes in
    await adapter.beforeRequest(structuredClone(prompt), 'model');
    expect(retrieves(h)).toBe(3);  // but the next request asks again
  });

  it('without a coverage read (HUD off, panel closed) a reroll still reuses the packet: the gap left open', async () => {
    const { h } = setup();
    const adapter = await h.start();
    await adapter.beforeRequest(structuredClone(prompt), 'model');
    await adapter.beforeRequest(structuredClone(prompt), 'model');
    expect(retrieves(h)).toBe(1);
  });

  it('reads what a coverage answer says memory holds', () => {
    expect(memoryMark(cov(1))).toBe(JSON.stringify([1, 4, null, 2, 0]));
    expect(memoryMark({})).toBeNull();
    expect(memoryMark(null)).toBeNull();
    expect(memoryMark({ extraction: { compiled: '3' } })).toBeNull();
  });
});

describe("recall's query on a Continue (G7)", () => {
  const char = (chatId: string, data: string, extra: Partial<HostMessage> = {}): HostMessage =>
    ({ role: 'char', data, chatId, ...extra });
  const user = (chatId: string, data: string, extra: Partial<HostMessage> = {}): HostMessage =>
    ({ role: 'user', data, chatId, ...extra });
  const long = `${'The harbor fog thickens over the pier. '.repeat(20)}Sera finally opens the archive door.`;

  it("asks with the end of the reply being continued, not the host's *says nothing* (useSayNothing on)", () => {
    for (const said of ['*says nothing*', 'Says nothing', ' *SAYS NOTHING* ']) {
      const out = queryTexts([user('u0', 'Open the archive.'), char('c0', long), user('u1', said)]);
      expect(out.isContinue).toBe(true);
      expect(out.previousAi).toBe(long);
      expect(out.query).toBe(long.slice(-CONTINUE_QUERY_TAIL));
      expect(out.query.endsWith('Sera finally opens the archive door.')).toBe(true);
    }
  });

  it('keeps the message as the query when no reply comes before it', () => {
    expect(queryTexts([user('u0', '*says nothing*')])).toEqual({ query: '*says nothing*', previousAi: '', isContinue: true });
  });

  it('asks beside the reply being continued, not the one before the user message (useSayNothing off)', () => {
    const out = queryTexts([char('c0', 'An old reply.'), user('u1', 'Open the archive.'), char('c1', 'Sera reaches for the door.'),
      char('c2', 'A disabled one.', { disabled: true })]);
    expect(out).toEqual({ query: 'Open the archive.', previousAi: 'Sera reaches for the door.', isContinue: true });
  });

  it('joins the last user messages sent in a row, oldest first, skipping disabled ones', () => {
    const out = queryTexts([char('c0', 'Sera waits.'), user('u1', 'First part.'), user('u2', 'Second part.'),
      user('u3', 'hidden', { disabled: true }), user('u4', 'Third part.'), user('u5', 'Fourth part.')]);
    expect(BURST_MESSAGES).toBe(3);
    expect(out).toEqual({ query: 'Second part.\nThird part.\nFourth part.', previousAi: 'Sera waits.', isContinue: false });
    const two = queryTexts([user('u0', 'Old turn.'), char('c0', 'Sera waits.'), user('u1', 'First part.'), user('u2', 'Second part.')]);
    expect(two.query).toBe('First part.\nSecond part.');  // stops at the reply
  });

  it('leaves an ordinary turn as it was', () => {
    expect(queryTexts([user('u0', 'Old turn.'), char('c0', 'Sera waits.'), user('u1', 'Where is the lantern?')]))
      .toEqual({ query: 'Where is the lantern?', previousAi: 'Sera waits.', isContinue: false });
  });

  it('sends the Continue query to the sidecar', async () => {
    const chat: HostChat = { id: 'chat-1', message: [user('u0', 'Open the archive.'), char('c0', long),
      user('u1', '*says nothing*')] };
    const continuePrompt: PromptMessage[] = [{ role: 'system', content: 'narrator' }, { role: 'user', content: 'Open the archive.' },
      { role: 'assistant', content: long }, { role: 'user', content: '*says nothing*' }, { role: 'system', content: 'continue' }];
    const h = harness();
    h.setChat(chat);
    await createAdapter(h.host, undefined, h.options).beforeRequest(continuePrompt, 'model');
    const retrieve = h.calls.find((c) => c.path === '/v1/retrieve')!.body;
    expect(retrieve.query).toBe(long.slice(-CONTINUE_QUERY_TAIL));
    expect(retrieve.previous_ai).toBe(long);
    expect(retrieve).not.toHaveProperty('is_continue');  // the request keeps its shape
  });
});
