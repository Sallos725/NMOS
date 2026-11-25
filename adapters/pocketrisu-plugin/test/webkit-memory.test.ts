import { describe, expect, it, vi } from 'vitest';
import { createAdapter, type HostPort, type Settings } from '../src/core';
import { createHud, type HudDeps, type HudDocument, type HudElement } from '../src/hud-host';
import { createManifestBuilder } from '../src/manifest';
import { inContextIds, matchPromptToHost } from '../src/prompt';
import type { HostChat, PromptMessage } from '../src/types';

function makeBigChat(id: string, count: number, charPerMsg: number): HostChat {
  const payload = 'a'.repeat(charPerMsg);
  return {
    id,
    message: Array.from({ length: count }, (_, i) => ({
      chatId: `${id}-m${i}`,
      role: i % 2 === 0 ? 'user' : 'char',
      data: `${i}:${payload}`,
    })),
  };
}

describe('iPhone Safari / WebKit memory & speed hardening', () => {
  it('evicts older giant chat from manifest cache when total retained chars exceed 12M, and clear() frees all', async () => {
    const build = createManifestBuilder();
    // 200 messages × 35,000 chars = ~7M chars each -> 2 chats = ~14M > 12M limit
    const bigA = makeBigChat('big-a', 200, 35_000);
    const bigB = makeBigChat('big-b', 200, 35_000);
    expect((await build(bigA, null)).hashed).toBe(200);
    expect((await build(bigA, null)).hashed).toBe(0); // stays warm alone
    expect((await build(bigB, null)).hashed).toBe(200); // evicts bigA because 14M > 12M
    expect((await build(bigB, null)).hashed).toBe(0); // bigB stays warm
    expect((await build(bigA, null)).hashed).toBe(200); // bigA was evicted
    build.clear();
    expect((await build(bigA, null)).hashed).toBe(200); // clear() released everything
  });

  it('reuses precomputed matchPromptToHost map in inContextIds with identical results', () => {
    const host = [
      { chatId: 'u0', role: 'user' as const, data: 'Earlier user turn with enough anchor characters here' },
      { chatId: 'c0', role: 'char' as const, data: 'Earlier assistant reply with enough anchor characters here' },
      { chatId: 'u1', role: 'user' as const, data: 'Latest user turn with enough anchor characters here' },
    ];
    const prompt: PromptMessage[] = [
      { role: 'system', content: 'System prompt' },
      { role: 'user', content: host[0]!.data! },
      { role: 'assistant', content: host[1]!.data! },
      { role: 'user', content: host[2]!.data! },
    ];
    const matches = matchPromptToHost(prompt, host);
    expect(inContextIds(prompt, host, undefined, undefined, matches)).toEqual(inContextIds(prompt, host));
    expect(inContextIds(prompt, host, undefined, undefined, matches)).toEqual(['u0', 'c0', 'u1']);
  });

  it('returnedMemo streaming digest deduplicates retries (string & multipart) and detects single-char edits', async () => {
    const settings: Settings = {
      sidecarUrl: 'http://127.0.0.1:8790',
      authToken: '',
      enabled: true,
      reservedMemoryTokens: 800,
      deadlineMs: 3000,
      injectPosition: 'before_last_user',
      route: 'direct',
      language: 'ko',
    };
    const chat: HostChat = {
      id: 'chat-memo',
      message: [
        { chatId: 'u1', role: 'user', data: 'Where did Sera hide the silver key last winter?' },
      ],
    };
    let retrieveCalls = 0;
    const host: HostPort = {
      settings: async () => settings,
      currentChat: async () => chat,
      request: async (_method, url) => {
        if (url.endsWith('/v1/sync/reconcile')) {
          return { status: 200, json: { conversation_id: 'c1', status: 'applied', active_commit: 'cm1', manifest_hash: 'mh1' } };
        }
        retrieveCalls++;
        return {
          status: 200,
          json: { freshness: 'fresh', packet: { text: '<NarrativeMemory version="0" source="nmos">\nFact line\n</NarrativeMemory>' } },
        };
      },
      warn: () => {},
      debug: () => {},
      now: () => 1000,
    };
    const adapter = createAdapter(host);
    // Use placeholder in a user block so stripMarkers leaves no system packet tag; returnedMemo must catch the retry
    const prompt: PromptMessage[] = [
      { role: 'user', content: [{ type: 'text', text: '[NMOS.memory]\nWhere did Sera hide the silver key last winter?' }] },
    ];
    const first = await adapter.beforeRequest(prompt, 'model');
    expect(retrieveCalls).toBe(1);
    // Retry with identical returned prompt -> returnedMemo short-circuits immediately
    const retry = await adapter.beforeRequest(first, 'model');
    expect(retry).toBe(first);
    expect(retrieveCalls).toBe(1);
    // Dispose releases caches without throwing
    adapter.dispose();
  });

  it('HUD dispose() clears timers, removes DOM element and listener, and ignores later events', async () => {
    const removedListeners: string[] = [];
    let removedEl = false;
    const timers = new Set<number>();
    let nextTimer = 1;
    const mkEl = (): HudElement => ({
      remove: async () => { removedEl = true; },
      appendChild: async () => {},
      addClass: async () => {},
      setStyleAttribute: async () => {},
      setStyle: async () => {},
      setTextContent: async () => {},
      setInnerHTML: async () => {},
      getBoundingClientRect: async () => ({ left: 0, top: 0, right: 10, bottom: 10 }),
      addEventListener: async () => 'lid-1',
      removeEventListener: async (_t, id) => { removedListeners.push(id); },
    });
    const doc: HudDocument = {
      querySelector: async (sel) => (sel === 'body' ? mkEl() : null),
      createElement: async () => mkEl(),
    };
    const deps: HudDeps = {
      enabled: async () => true,
      lang: async () => 'ko',
      rootDocument: async () => doc,
      position: async () => '0:0',
      coverage: async () => ({ extraction: { generation: 'g', eligible: 5, compiled: 1, pending: 4, failed: 0 } }),
      openPanel: () => {},
      now: () => 1000,
      debug: () => {},
      setTimer: () => { const id = nextTimer++; timers.add(id); return id; },
      clearTimer: (h) => { timers.delete(h as number); },
    };
    const hud = createHud(deps);
    hud.event({ type: 'request-end', outcome: 'injected', chars: 120, conversationId: 'conv-1' });
    await hud.settled();
    expect(timers.size).toBeGreaterThan(0);

    hud.dispose();
    await vi.waitFor(() => expect(removedEl).toBe(true));
    expect(timers.size).toBe(0);
    expect(removedListeners).toEqual(['lid-1']);

    // Further events after dispose do not schedule any timer
    hud.event({ type: 'request-start' });
    await hud.settled();
    expect(timers.size).toBe(0);
  });
});
