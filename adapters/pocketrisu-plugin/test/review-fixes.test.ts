// Fixes from the independent review of the plugin at `de8f962` (findings 1–3, 5–8, nits 9–12). Synthetic chats only.

import { describe, expect, it } from 'vitest';
import { createAdapter, type HostPort, type HttpResult, type Settings } from '../src/core';
import { MEMORY_MARKER } from '../src/placement';
import { hasPacket, PACKET_TAG } from '../src/prompt';
import { trimPrompt } from '../src/trim';
import type { HostChat, HostMessage, PromptMessage } from '../src/types';

const PACKET = `${PACKET_TAG}\n  <Excerpt turn="0" speaker="user">lantern</Excerpt>\n</NarrativeMemory>`;
const asPrompt = (host: HostMessage[], system = 'Narrator.'): PromptMessage[] => [
  { role: 'system', content: system },
  ...host.map((m) => ({ role: m.role === 'user' ? 'user' : 'assistant', content: m.data })),
];
const chatOf = (): HostMessage[] => [
  { role: 'user', data: 'Sera found the silver key under the stone bench in the courtyard.', chatId: 'u0' },
  { role: 'char', data: 'Kaito examined the engraving on the silver key by lantern light.', chatId: 'c0' },
  { role: 'user', data: 'Hana brought the ledger from the harbor warehouse before midnight.', chatId: 'u1' },
  { role: 'char', data: 'Yuna compared the harbor ledger with the old watchtower manifest.', chatId: 'c1' },
  { role: 'user', data: 'Sera asked whether the north gate bell still rings at dawn.', chatId: 'u2' },
];
const packets = (prompt: PromptMessage[]) => JSON.stringify(prompt).split(PACKET_TAG.replace(/"/g, '\\"')).length - 1;

type Answer = (path: string, body: any) => HttpResult | Promise<HttpResult>;
function makeHost(held: () => HostChat, answer: Answer, overrides: Partial<Settings> = {}) {
  const calls: { path: string; body: any }[] = [];
  const host: HostPort = {
    settings: async () => ({ sidecarUrl: 'http://s', authToken: '', enabled: true, reservedMemoryTokens: 600,
      deadlineMs: 5000, injectPosition: 'before_last_user', route: 'direct', language: 'en', ...overrides }),
    currentChat: async () => structuredClone(held()),
    request: async (_m, url, body) => {
      const path = url.replace('http://s', '');
      calls.push({ path, body });
      if (path === '/v1/sync/reconcile') {
        return { status: 200, json: { status: 'noop', active_commit: 'c', manifest_hash: 'm', conversation_id: 'v' } };
      }
      return answer(path, body);
    },
    warn: () => {}, debug: () => {}, now: () => performance.now(),
  };
  return { host, calls, retrieves: () => calls.filter((c) => c.path === '/v1/retrieve') };
}
const fresh = (text: string, trim?: unknown): HttpResult => ({ status: 200, json: { freshness: 'fresh', packet: { text },
  ...(trim ? { trim } : {}) } });

describe('finding 1: a trimmed prompt never goes without the packet', () => {
  it('a short old chat message holding the literal is dropped: the packet is injected instead, once', async () => {
    const base = chatOf();
    const message: HostMessage[] = [base[0]!, base[1]!, { role: 'user', data: `${MEMORY_MARKER}?`, chatId: 'uM' },
      { role: 'char', data: 'Kaito shrugged and turned the brass key over in his palm twice.', chatId: 'cM' },
      base[2]!, base[3]!, base[4]!];
    const held: HostChat = { id: 'chat-1', message };
    const { host } = makeHost(() => held, (path, body) => (path !== '/v1/retrieve' ? { status: 200, json: {} }
      : body.trim ? fresh(PACKET, { keep_from_id: 'u1', keep_from_turn: 2, reason: null }) : fresh(PACKET)),
    { trimOldTurns: true, keepRecentTurns: 4 });
    const adapter = createAdapter(host);
    const prompt = asPrompt(message);
    const out = await adapter.beforeRequest(prompt, 'model');
    expect(packets(out)).toBe(1);
    expect(out).toHaveLength(prompt.length - 4 + 1);  // u0, c0, uM, cM left out; the packet in their place
    expect(out[out.length - 2]).toEqual({ role: 'system', content: PACKET });
    const last = (await adapter.status()).last!;
    expect(last.outcome).toBe('injected');
    expect(last.trim?.dropped).toBe(4);
  });
});

describe('finding 2: a whole packet in any non-system block is a retry', () => {
  it('an assistant-role placeholder block holding the packet, unless the chat itself holds it', () => {
    const host = chatOf();
    const prompt: PromptMessage[] = [...asPrompt(host).slice(0, -1), { role: 'assistant', content: `[Memory]\n${PACKET}` },
      asPrompt(host).at(-1)!];
    expect(hasPacket(prompt)).toBe(false);  // without the chat only a system message counts, as before
    expect(hasPacket(prompt, host)).toBe(true);
    const pasted: HostMessage[] = [...host.slice(0, 3), { role: 'char', data: `look: ${PACKET}`, chatId: 'c1' }, host[4]!];
    expect(hasPacket(asPrompt(pasted), pasted)).toBe(false);
  });

  it('a retry of a trimmed prompt whose packet sits in an assistant block, rewritten on the way: no second packet', async () => {
    const message = chatOf();
    const held: HostChat = { id: 'chat-2', message };
    const { host, retrieves } = makeHost(() => held, (path, body) => (path !== '/v1/retrieve' ? { status: 200, json: {} }
      : body.trim ? fresh(PACKET, { keep_from_id: 'u1', keep_from_turn: 1, reason: null }) : fresh(PACKET)),
    { trimOldTurns: true, keepRecentTurns: 4 });
    const adapter = createAdapter(host);
    const prompt = asPrompt(message);
    prompt.splice(5, 0, { role: 'assistant', content: `[Memory]\n${MEMORY_MARKER}` });
    const first = await adapter.beforeRequest(prompt, 'model');
    expect(packets(first)).toBe(1);
    expect(first.length).toBeLessThan(prompt.length);
    // The host retries; a request trigger rewrote the system block, so the prompt is no longer the one returned.
    const retry = structuredClone(first);
    retry[0] = { role: 'system', content: 'Narrator. (rewritten)' };
    const out = await adapter.beforeRequest(retry, 'model');
    expect(packets(out)).toBe(1);
    expect(retrieves()).toHaveLength(1);
  });
});

describe('finding 3: the backward walk never leaves the chat', () => {
  it("keeps a preset's own one-word acknowledgement above a system block, the same text as a reply not in the prompt", () => {
    const base = chatOf();
    const host: HostMessage[] = [base[0]!, { role: 'char', data: 'Okay.', chatId: 'c-ok' }, ...base.slice(2)];
    // The host's context holds u1 onward; the preset has its own "Okay." and a new-chat block above the chat.
    const prompt: PromptMessage[] = [{ role: 'system', content: 'Narrator.' }, { role: 'assistant', content: 'Okay.' },
      { role: 'system', content: '[Start a new chat]' }, ...asPrompt(host.slice(2)).slice(1)];
    const res = trimPrompt(prompt, host, 'u2');
    expect(res.reason).toBeNull();
    expect(res.dropped).toBe(2);
    expect(res.prompt.map((m) => m.content)).toEqual(['Narrator.', 'Okay.', '[Start a new chat]', base[4]!.data]);
  });

  it('still walks past depth blocks inside the chat', () => {
    const host = chatOf();
    const prompt = asPrompt(host);
    prompt.splice(2, 0, { role: 'system', content: '@D lore.' });
    const res = trimPrompt(prompt, host, 'u1');
    expect(res.reason).toBeNull();
    expect(res.prompt.map((m) => m.content)).toEqual(['Narrator.', '@D lore.', ...host.slice(2).map((m) => m.data)]);
  });
});

describe('finding 7: a short turn when nothing of the chat anchor-matches', () => {
  // Short user messages, and replies whose middle is a status block the request strips: nothing can match.
  const reply = (story: string, id: string): HostMessage => ({ role: 'char', chatId: id,
    data: `${story}\n<div class="status">HP 10/10 · MP 4/9 · Location: the old watchtower stairs · Weather: rain, wind from the north · Time: dusk</div>` });
  const stories = ['Kaito nodded and handed over the lantern.', 'Yuna laughed and closed the ledger.'];
  const host: HostMessage[] = [{ role: 'user', data: '응', chatId: 'u0' }, reply(stories[0]!, 'c0'),
    { role: 'user', data: 'ok', chatId: 'u1' }, reply(stories[1]!, 'c1'), { role: 'user', data: '네', chatId: 'u2' }];
  const dialogue: PromptMessage[] = [{ role: 'system', content: 'Narrator.' }, { role: 'user', content: '응' },
    { role: 'assistant', content: stories[0]! }, { role: 'user', content: 'ok' }, { role: 'assistant', content: stories[1]! }];

  it('accepts a prompt with dialogue whose newest user message is exactly the turn', async () => {
    const { userTurnIndex, matchPromptToHost } = await import('../src/prompt');
    const prompt = [...dialogue, { role: 'user', content: '네' }];
    expect(matchPromptToHost(prompt, host).size).toBe(0);
    expect(userTurnIndex(prompt, host)).toBe(5);
  });

  it('still rejects the word inside a longer newest user message, and a prompt with no dialogue', async () => {
    const { userTurnIndex } = await import('../src/prompt');
    expect(userTurnIndex([...dialogue, { role: 'user', content: '답: 네 맞아요, 다음 질문으로' }], host)).toBe(-1);
    expect(userTurnIndex([{ role: 'system', content: '판단하라' }, { role: 'user', content: '네' }], host)).toBe(-1);
  });
});

describe('finding 8: a system block never beats a newer holder of the other role', () => {
  it('the chat sent in user-role blocks, with an older recap quoting a reply: every message is in context', async () => {
    const { inContextIds } = await import('../src/prompt');
    const host = chatOf();
    const prompt: PromptMessage[] = [{ role: 'system', content: `Recap: ${host[3]!.data}` },
      ...host.map((m) => ({ role: 'user', content: m.data }))];
    expect(inContextIds(prompt, host)).toEqual(['u0', 'c0', 'u1', 'c1', 'u2']);
  });
});
