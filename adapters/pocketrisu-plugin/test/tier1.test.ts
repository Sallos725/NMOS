// Tier 1 plugin fixes: reasoning blocks, "Cut Messages for AI", multipart text, short user turns, the retry guard for
// a packet in a user block, `[NMOS.memory]` in chat history, trimming relaxations and the split-brain guard, canon
// trigger keys, the card refresh and the empty-packet cache. Synthetic chats only.

import { describe, expect, it, vi } from 'vitest';
import { canonTexts, heldKeys, type HostCard, type HostLoreEntry } from '../src/canon';
import { createAdapter, type HostPort, type HttpResult, type Settings } from '../src/core';
import { DEFAULT_KEEP_RECENT_TURNS } from '../src/form';
import { findMarker, MEMORY_MARKER, resolvePlaceholders } from '../src/placement';
import { activeStartIndex, cleanText, contentText, hasPacket, historyMarkerIndices, inContextIds, isActive,
  latestUserIndex, matchPromptToHost, PACKET_TAG, queryTexts, userTurnIndex, withGuard } from '../src/prompt';
import { canonicalJson } from '../src/canonical';
import { canTrimPrompt, trimPrompt } from '../src/trim';
import type { HostChat, HostMessage, PromptMessage } from '../src/types';

const PACKET = `${PACKET_TAG}\n  <Excerpt turn="0" speaker="user">lantern</Excerpt>\n</NarrativeMemory>`;
const asPrompt = (host: HostMessage[], system = 'Narrator.'): PromptMessage[] => [
  { role: 'system', content: system },
  ...host.map((m) => ({ role: m.role === 'user' ? 'user' : 'assistant', content: m.data })),
];
const chatOf = (): HostMessage[] => [
  { role: 'user', data: '세라 found the silver key under the stone bench in the courtyard.', chatId: 'u0' },
  { role: 'char', data: '카이토 examined the engraving on the silver key by lantern light.', chatId: 'c0' },
  { role: 'user', data: '하나 brought the ledger from the harbor warehouse before midnight.', chatId: 'u1' },
  { role: 'char', data: '유나 compared the harbor ledger with the old watchtower manifest.', chatId: 'c1' },
  { role: 'user', data: '세라 asked whether the north gate bell still rings at dawn.', chatId: 'u2' },
];

describe('reasoning blocks (cleanText)', () => {
  it('drops <Thoughts>, <think> and <thinking> blocks like the sidecar, and keeps an unclosed tag as text', () => {
    expect(cleanText('<Thoughts>plan the scene</Thoughts>She smiled.')).toBe('She smiled.');
    expect(cleanText('<think>a</think>One<THINKING x="1">b</thinking> two')).toBe('One two');
    expect(cleanText('<think>never closed, so kept')).toBe('never closed, so kept');
  });

  it('matches a reply whose reasoning the host sent apart, so it counts as in context', () => {
    const reply = '카이토 lifted the lantern and led 세라 down the spiral stairs of the watchtower.';
    const host: HostMessage[] = [
      { role: 'user', data: '세라 asked 카이토 to show her the way down to the cellar.', chatId: 'u0' },
      { role: 'char', data: `<Thoughts>${'The user wants a descent scene; keep it tense and slow. '.repeat(6)}</Thoughts>${reply}`,
        chatId: 'c0' },
      { role: 'user', data: '세라 asked what was waiting at the bottom of the stairs.', chatId: 'u1' },
    ];
    const prompt: PromptMessage[] = [{ role: 'system', content: 'Narrator.' },
      { role: 'user', content: host[0]!.data }, { role: 'assistant', content: reply, thoughts: ['…'] },
      { role: 'user', content: host[2]!.data }];
    expect(matchPromptToHost(prompt, host)).toEqual(new Map([[2, 3], [1, 2], [0, 1]]));
    expect(inContextIds(prompt, host)).toEqual(['u0', 'c0', 'u1']);
  });
});

describe('"Cut Messages for AI" (disabled: allBefore, HOST-FACTS S8b)', () => {
  const cut = (): HostMessage[] => {
    const host = chatOf();
    host[2] = { ...host[2]!, disabled: 'allBefore' };
    return host;
  };

  it('hides the cut message and every message before it', () => {
    const host = cut();
    expect(activeStartIndex(host)).toBe(3);
    expect(activeStartIndex(chatOf())).toBe(0);
    expect(isActive(host[2])).toBe(false);
    expect(latestUserIndex(host)).toBe(4);
    expect(latestUserIndex([host[0]!, { ...host[2]!, chatId: 'only' }])).toBe(-1);
  });

  it('leaves the hidden part out of the AI message before the turn and of the prompt match', () => {
    const host: HostMessage[] = [...chatOf().slice(0, 4), { role: 'user', data: 'cut here', chatId: 'cut',
      disabled: 'allBefore' }, { role: 'user', data: '세라 asked whether the north gate bell still rings at dawn.', chatId: 'u2' }];
    expect(queryTexts(host).previousAi).toBe('');
    expect(queryTexts(chatOf()).previousAi).toBe(chatOf()[3]!.data);
    // A preset block quoting a hidden reply is no evidence that it is in context.
    const prompt: PromptMessage[] = [{ role: 'system', content: `Earlier: ${host[3]!.data}` }, { role: 'user', content: host[5]!.data }];
    expect(matchPromptToHost(prompt, host)).toEqual(new Map([[5, 1]]));
    expect(inContextIds(prompt, host)).toEqual(['u2']);
  });

  it('never trims at a boundary the cut hides', () => {
    const host = cut();
    expect(trimPrompt(asPrompt(host), host, 'c0').reason).toBe('format');
  });
});

describe('multipart text (contentText)', () => {
  it('joins text parts, ignores images, and has no text for other shapes', () => {
    expect(contentText([{ type: 'text', text: 'a "b"' }, { type: 'image_url', image_url: { url: 'x' } },
      { type: 'text', text: 'c\nd' }])).toBe('a "b"\nc\nd');
    expect(contentText([{ type: 'image_url', image_url: { url: 'x' } }])).toBe('');
    expect(contentText({ weird: 1 })).toBe('');
    expect(contentText(null)).toBe('');
  });

  it('finds a user turn with quotes and line breaks sent with an image', () => {
    const host: HostMessage[] = [{ role: 'user', data: '세라 said "wait here"\nand walked toward the harbor gate alone.',
      chatId: 'u0' }];
    const prompt: PromptMessage[] = [{ role: 'system', content: 'Narrator.' }, { role: 'user', content: [
      { type: 'image_url', image_url: { url: 'https://example.invalid/p.png' } }, { type: 'text', text: host[0]!.data }] }];
    expect(userTurnIndex(prompt, host)).toBe(1);
  });
});

describe('short user turns (userTurnIndex)', () => {
  const history = chatOf().slice(0, 4);
  const withTurn = (data: string): HostMessage[] => [...history, { role: 'user', data, chatId: 'u2' }];

  it('takes the message that is the turn, not a word holding it in an instruction block after it', () => {
    const host = withTurn('응');
    const prompt: PromptMessage[] = [...asPrompt(history), { role: 'user', content: '응' },
      { role: 'system', content: '캐릭터의 반응을 자세히 묘사하라.' }];
    expect(userTurnIndex(prompt, host)).toBe(5);
  });

  it('takes a user message holding the turn as a word of its own, past a preset wrapper', () => {
    const host = withTurn('go');
    const prompt: PromptMessage[] = [...asPrompt(history), { role: 'user', content: '[Input] go [/Input]' },
      { role: 'system', content: 'Keep going; ongoing scenes stay ongoing.' }];
    expect(userTurnIndex(prompt, host)).toBe(5);
  });

  it('rejects an auxiliary call with none of the chat in it', () => {
    const host = withTurn('네');
    expect(userTurnIndex([{ role: 'system', content: '다음 답이 긍정인지 판단하라: 네' }], host)).toBe(-1);
    expect(userTurnIndex([{ role: 'user', content: '네' }], host)).toBe(-1);
    // A chat with nothing long enough to match cannot tell: the exact turn is taken.
    expect(userTurnIndex([{ role: 'user', content: '네' }], [{ role: 'user', data: '네', chatId: 'u0' }])).toBe(0);
  });

  it('never takes an older identical short message over the wrapped current turn', () => {
    const host: HostMessage[] = [...history, { role: 'user', data: '응', chatId: 'u-old' },
      { role: 'char', data: '카이토 nodded and pointed at the lantern hanging over the harbor gate.', chatId: 'c-old' },
      { role: 'user', data: '응', chatId: 'u2' }];
    const prompt: PromptMessage[] = [...asPrompt(host.slice(0, 6)),
      { role: 'user', content: '<user_input>응</user_input>\n(OOC: stay in character)' }];
    expect(userTurnIndex(prompt, host)).toBe(7);
  });

  it('prefers a prompt message of the fitting role and falls back to the other', () => {
    const host: HostMessage[] = [{ role: 'user', data: 'Where did we hide the bronze lantern last winter?', chatId: 'u0' }];
    const both: PromptMessage[] = [{ role: 'user', content: host[0]!.data },
      { role: 'assistant', content: `You asked: ${host[0]!.data}` }];
    expect(matchPromptToHost(both, host)).toEqual(new Map([[0, 0]]));
    expect(matchPromptToHost([both[1]!], host)).toEqual(new Map([[0, 0]]));
  });
});

describe('retry guard (hasPacket)', () => {
  const host = chatOf();

  it('sees a whole packet a placeholder put in a user block, given the chat', () => {
    const prompt: PromptMessage[] = [...asPrompt(host).slice(0, -1), { role: 'user', content: `${host[4]!.data}\n${PACKET}` }];
    expect(hasPacket(prompt)).toBe(false); // without the chat only a system message counts, as before
    expect(hasPacket(prompt, host)).toBe(true);
  });

  it('ignores the tag quoted in a user message and a packet the chat itself holds', () => {
    expect(hasPacket([{ role: 'user', content: `What is ${PACKET_TAG}?` }], host)).toBe(false);
    const pasted: HostMessage[] = [...host.slice(0, 4), { role: 'user', data: `look: ${PACKET}`, chatId: 'u2' }];
    expect(hasPacket(asPrompt(pasted), pasted)).toBe(false);
  });
});

describe('[NMOS.memory] in chat history', () => {
  const host = chatOf();
  host[1] = { ...host[1]!, data: `${host[1]!.data} The note said ${MEMORY_MARKER}.` };

  it('skips a chat message that mentions the placeholder, not a preset placeholder in a chat message', () => {
    const prompt = asPrompt(host);
    prompt.splice(4, 0, { role: 'system', content: `Memory:\n${MEMORY_MARKER}` });
    const skip = historyMarkerIndices(prompt, host);
    expect([...skip]).toEqual([2]);
    expect(findMarker(prompt)).toEqual({ message: 2, part: null, offset: expect.any(Number) });
    expect(findMarker(prompt, skip)).toEqual({ message: 4, part: null, offset: 8 });
    const out = resolvePlaceholders(prompt, PACKET, skip);
    expect(out[2]).toBe(prompt[2]);
    expect(out[4]?.content).toBe(`Memory:\n${PACKET}`);
    // A marker the host message does not hold is the preset's.
    const preset = asPrompt(chatOf());
    preset[2] = { ...preset[2]!, content: `${preset[2]!.content as string}\n${MEMORY_MARKER}` };
    expect(historyMarkerIndices(preset, chatOf()).size).toBe(0);
  });

  it('lets a trim drop a chat message that mentions the placeholder', () => {
    const res = trimPrompt(asPrompt(host), host, 'u1');
    expect(res.reason).toBeNull();
    expect(res.dropped).toBe(2);
  });
});

describe('trimming relaxations', () => {
  it('drops a message with name and removable, and moves its cache point to the first message kept', () => {
    const host = chatOf();
    const prompt = asPrompt(host).map((m, i) => (i === 1 ? { ...m, name: '세라', removable: true }
      : i === 2 ? { ...m, cachePoint: true } : m));
    const res = trimPrompt(prompt, host, 'u1');
    expect(res.reason).toBeNull();
    expect(res.dropped).toBe(2);
    expect(res.prompt[1]).toEqual({ ...prompt[3], cachePoint: true });
    expect(prompt[3]).not.toHaveProperty('cachePoint'); // a copy, never the input
    expect(res.prompt[0]).toBe(prompt[0]);
    // A kept message with its own cache point keeps it, and a false one moves nothing.
    const own = prompt.map((m, i) => (i === 3 ? { ...m, cachePoint: true } : m));
    expect(trimPrompt(own, host, 'u1').prompt[1]).toBe(own[3]);
    const off = asPrompt(host).map((m, i) => (i === 2 ? { ...m, cachePoint: false } : m));
    expect(trimPrompt(off, host, 'u1').prompt[1]).toBe(off[3]);
  });

  it('keeps several depth blocks between dropped chat messages, and still refuses a chat message sent as system', () => {
    const host = chatOf();
    const prompt = asPrompt(host);
    prompt.splice(3, 0, { role: 'system', content: '@D lore one.' }, { role: 'system', content: '@D lore two.' });
    const res = trimPrompt(prompt, host, 'u1');
    expect(res.reason).toBeNull();
    expect(res.prompt.map((m) => m.content)).toEqual(['Narrator.', '@D lore one.', '@D lore two.', ...host.slice(2).map((m) => m.data)]);
    const asSystem = asPrompt(host);
    asSystem[2] = { role: 'system', content: host[1]!.data };
    expect(trimPrompt(asSystem, host, 'u1').reason).toBe('format');
  });

  it('pre-flight: a prompt that can take a cut, and ones that cannot', () => {
    const host = chatOf();
    expect(canTrimPrompt(asPrompt(host), host)).toBe(true);
    const merged: PromptMessage[] = [{ role: 'system', content: 'Narrator.' },
      { role: 'user', content: host.map((m) => m.data).join('\n') }];
    expect(canTrimPrompt(merged, host)).toBe(false);
    const image = asPrompt(host).map((m, i) => (i === 1 ? { ...m, multimodals: [{ type: 'image' }] } : m));
    expect(canTrimPrompt(image, host)).toBe(false);
    expect(canTrimPrompt([{ role: 'system', content: 'Narrator.' }, { role: 'user', content: host[4]!.data }], host)).toBe(false);
  });

  it('steps by 16 turns by default (a multiple of the 8-turn window)', () => {
    expect(DEFAULT_KEEP_RECENT_TURNS).toBe(16);
  });
});

describe('canon (trigger keys, multipart prompt)', () => {
  const chat: HostChat = { id: 'chat-1', message: [] };
  const entry = (extra: Partial<HostLoreEntry>): HostLoreEntry => ({ id: 'e1', key: '카이토, 카이', comment: '카이토',
    content: '카이토는 등대의 기사다.', mode: 'normal', ...extra });

  it('keeps secondary keys apart from the names, and leaves an entry without them as it was', () => {
    const [selective] = canonTexts(null, chat, [entry({ secondkey: '비밀, 흉터' })], null);
    expect(selective!.metadata.keys).toEqual(['카이토', '카이']);
    expect(selective!.metadata.trigger_keys).toEqual(['비밀', '흉터']);
    const [plain] = canonTexts(null, chat, [entry({ secondkey: ' ' })], null);
    expect(plain!.metadata.trigger_keys).toBeUndefined();
    expect(canonicalJson(plain!.metadata)).not.toContain('trigger_keys'); // hashed as before
    expect(plain!.metadata.keys).toEqual(['카이토', '카이']);
  });

  it('finds canon held in a multipart prompt message', () => {
    const texts = canonTexts(null, chat, [entry({})], null);
    const prompt: PromptMessage[] = [{ role: 'system', content: [{ type: 'text', text: '카이토는 등대의 기사다.' },
      { type: 'image_url', image_url: { url: 'x' } }] }];
    expect(heldKeys(texts, prompt)).toEqual(['lore:e1']);
  });
});

describe('request path (core)', () => {
  type Answer = (body: any, n: number) => HttpResult | Promise<HttpResult>;
  function makeHost(held: HostChat, answer: Answer, overrides: Partial<Settings> = {}) {
    const bodies: any[] = [];
    let now = 1_000;
    const host: HostPort = {
      settings: async () => ({ sidecarUrl: 'http://s', authToken: '', enabled: true, reservedMemoryTokens: 600,
        deadlineMs: 5000, injectPosition: 'before_last_user', route: 'direct', language: 'en', ...overrides }),
      currentChat: async () => held,
      request: async (_m, url, body) => {
        const path = url.replace('http://s', '');
        if (path === '/v1/sync/reconcile') {
          return { status: 200, json: { status: 'noop', active_commit: 'c', manifest_hash: 'm', conversation_id: 'v' } };
        }
        if (path === '/v1/retrieve') {
          bodies.push(body);
          return answer(body, bodies.length);
        }
        return { status: 200, json: {} };
      },
      warn: () => {}, debug: () => {}, now: () => now,
    };
    return { host, bodies, advance: (ms: number) => { now += ms; } };
  }
  const fresh = (text: string, trim?: unknown): HttpResult => ({ status: 200, json: { freshness: 'fresh', packet: { text },
    ...(trim ? { trim } : {}) } });

  it('never places a packet built for a boundary the prompt refuses: fetches one without a cut, once', async () => {
    const held: HostChat = { id: 'chat-t', message: chatOf() };
    const prompt = asPrompt(held.message);
    prompt[3] = { ...prompt[3]!, multimodals: [{ type: 'image' }] }; // u1 carries an image: no cut past it
    const pre = `${PACKET_TAG}\n  <Excerpt turn="0" speaker="user">built without u0..c1</Excerpt>\n</NarrativeMemory>`;
    const { host, bodies } = makeHost(held, (body) => (body.trim
      ? fresh(pre, { keep_from_id: 'u2', keep_from_turn: 2, reason: null }) : fresh(PACKET)),
    { trimOldTurns: true, keepRecentTurns: 4 });
    const adapter = createAdapter(host);
    const out = await adapter.beforeRequest(prompt, 'model');
    expect(bodies.map((b) => !!b.trim)).toEqual([true, false]);
    expect(JSON.stringify(out)).not.toContain('built without');
    expect(out).toHaveLength(prompt.length + 1);
    expect(out[out.length - 2]?.content).toBe(PACKET);
    expect((await adapter.status()).last?.trim).toEqual({ dropped: 0, savedTokens: 0, reason: 'format', keepFromTurn: null });
    // The next request of the same state asks no boundary and reuses the packet fetched without one.
    await adapter.beforeRequest(structuredClone(prompt), 'model');
    expect(bodies).toHaveLength(2);
  });

  it('fails open when the packet fetched without a cut fails or misses the deadline', async () => {
    const pre = `${PACKET_TAG}\n  <Excerpt turn="0" speaker="user">built without u0..c1</Excerpt>\n</NarrativeMemory>`;
    for (const late of [false, true]) {
      const held: HostChat = { id: `chat-f${late}`, message: chatOf() };
      const prompt = asPrompt(held.message);
      prompt[3] = { ...prompt[3]!, multimodals: [{ type: 'image' }] };
      const { host, bodies } = makeHost(held, (body) => (body.trim
        ? fresh(pre, { keep_from_id: 'u2', keep_from_turn: 2, reason: null })
        : late ? new Promise<HttpResult>((r) => setTimeout(() => r(fresh(PACKET)), 300)) : { status: 500, json: null }),
      { trimOldTurns: true, keepRecentTurns: 4, deadlineMs: 100 });
      const adapter = createAdapter(host);
      const out = await adapter.beforeRequest(prompt, 'model');
      expect(out, String(late)).toEqual(prompt);
      expect(JSON.stringify(out)).not.toContain('built without');
      expect(bodies.map((b) => !!b.trim)).toEqual([true, false]);
      expect((await adapter.status()).last).toMatchObject({ outcome: 'failed',
        trim: { dropped: 0, savedTokens: 0, reason: 'failed', keepFromTurn: null } });
    }
  });

  it('a cached boundary the prompt now refuses is not served: the packet is fetched without a cut', async () => {
    const held: HostChat = { id: 'chat-h', message: chatOf() };
    const pre = `${PACKET_TAG}\n  <Excerpt turn="0" speaker="user">built without u0..c1</Excerpt>\n</NarrativeMemory>`;
    const { host, bodies } = makeHost(held, (body) => (body.trim
      ? fresh(pre, { keep_from_id: 'u2', keep_from_turn: 2, reason: null }) : fresh(PACKET)),
    { trimOldTurns: true, keepRecentTurns: 4 });
    const adapter = createAdapter(host);
    const plain = asPrompt(held.message);
    const first = await adapter.beforeRequest(plain, 'model');
    expect(first).toHaveLength(3); // u0..c1 left out, the pre-cut packet in their place
    expect(JSON.stringify(first)).toContain('built without');
    // The same chat state and prompt length, but u1 now carries an image: the cached boundary cannot apply.
    const image = asPrompt(held.message);
    image[3] = { ...image[3]!, multimodals: [{ type: 'image' }] };
    const out = await adapter.beforeRequest(image, 'model');
    // No boundary is asked for again in that request (review nit 10: it was [true, true, false]).
    expect(bodies.map((b) => !!b.trim)).toEqual([true, false]);
    expect(JSON.stringify(out)).not.toContain('built without');
    expect(out).toHaveLength(image.length + 1);
    expect((await adapter.status()).last?.trim?.reason).toBe('format');
    // The packet without a cut is kept under the key the next request has: served from the cache.
    await adapter.beforeRequest(structuredClone(image), 'model');
    expect(bodies).toHaveLength(2);
  });

  it('a non-fresh answer is not remembered as an empty packet (review nit 11)', async () => {
    const held: HostChat = { id: 'chat-st', message: chatOf() };
    const { host, bodies } = makeHost(held, (_body, n) => (n === 1
      ? { status: 200, json: { freshness: 'stale', packet: { text: '' } } } : fresh(PACKET)));
    const adapter = createAdapter(host);
    const prompt = asPrompt(held.message);
    expect(await adapter.beforeRequest(prompt, 'model')).toEqual(prompt);
    const out = await adapter.beforeRequest(structuredClone(prompt), 'model');
    expect(bodies).toHaveLength(2);
    expect(JSON.stringify(out)).toContain('lantern');
  });

  it('asks for no boundary when the prompt holds no dialogue a cut could drop', async () => {
    const held: HostChat = { id: 'chat-p', message: chatOf() };
    const { host, bodies } = makeHost(held, () => fresh(PACKET), { trimOldTurns: true, keepRecentTurns: 4 });
    const prompt: PromptMessage[] = [{ role: 'system', content: 'Narrator.' }, { role: 'user', content: held.message[4]!.data }];
    const adapter = createAdapter(host);
    await adapter.beforeRequest(prompt, 'model');
    expect(bodies[0]).not.toHaveProperty('trim');
    expect((await adapter.status()).last?.trim?.reason).toBe('format');
  });

  it('makes no call for a retry whose packet sits in a user block', async () => {
    const held: HostChat = { id: 'chat-r', message: chatOf() };
    const { host, bodies } = makeHost(held, () => fresh(PACKET));
    const prompt = asPrompt(held.message);
    prompt[prompt.length - 1] = { role: 'user', content: `${held.message[4]!.data}\n${MEMORY_MARKER}` };
    const adapter = createAdapter(host);
    const out = await adapter.beforeRequest(prompt, 'model');
    expect(out[out.length - 1]?.content).toBe(`${held.message[4]!.data}\n${withGuard(PACKET)}`);
    // A copy (not the memoised array) of the injected prompt, as a host retry would send it.
    expect(await adapter.beforeRequest(structuredClone(out), 'model')).toEqual(out);
    expect(bodies).toHaveLength(1);
  });

  it('places the packet at the preset placeholder when an old chat message mentions [NMOS.memory]', async () => {
    const message = chatOf();
    message[1] = { ...message[1]!, data: `${message[1]!.data} Write ${MEMORY_MARKER} here.` };
    const held: HostChat = { id: 'chat-m', message };
    const { host } = makeHost(held, () => fresh(PACKET));
    const prompt = asPrompt(message);
    prompt.splice(5, 0, { role: 'system', content: `[Memory]\n${MEMORY_MARKER}` });
    const out = await createAdapter(host).beforeRequest(prompt, 'model');
    expect(out).toHaveLength(prompt.length);
    expect(out[5]?.content).toBe(`[Memory]\n${PACKET}`);
    expect(out[2]?.content).not.toContain(PACKET_TAG);
    expect(JSON.stringify(out)).not.toContain(MEMORY_MARKER);
  });

  it('reuses an empty packet briefly only, and not after a reply, while a packet with memory stays', async () => {
    const held: HostChat = { id: 'chat-e', message: chatOf() };
    let text = '';
    const { host, bodies, advance } = makeHost(held, () => fresh(text));
    const adapter = createAdapter(host);
    const prompt = asPrompt(held.message);
    await adapter.beforeRequest(structuredClone(prompt), 'model');
    await adapter.beforeRequest(structuredClone(prompt), 'model');
    expect(bodies).toHaveLength(1);
    advance(61_000);
    await adapter.beforeRequest(structuredClone(prompt), 'model');
    expect(bodies).toHaveLength(2); // an empty packet is kept a minute, not ten
    adapter.onOutput({ chat: held, messageIndex: 4 });
    await new Promise((r) => setTimeout(r, 0));
    await adapter.beforeRequest(structuredClone(prompt), 'model');
    expect(bodies).toHaveLength(3); // a reply came: the empty packet is not reused
    text = PACKET;
    advance(61_000);
    await adapter.beforeRequest(structuredClone(prompt), 'model');
    adapter.onOutput({ chat: held, messageIndex: 4 });
    await new Promise((r) => setTimeout(r, 0));
    await adapter.beforeRequest(structuredClone(prompt), 'model');
    expect(bodies).toHaveLength(4); // a reroll of the unchanged chat reuses the packet with memory
  });

  it('reads the card again when its personality drops out of the prompt that held it', async () => {
    const message: HostMessage[] = [{ role: 'user', data: '세라 asked whether the north gate bell still rings at dawn.',
      chatId: 'u0' }];
    const held: HostChat = { id: 'chat-c', message };
    const card: HostCard = { name: '하나', desc: '하나는 항구 마을 등대지기의 딸이다.', personality: '밝고 고집이 세다, 늘 웃는다.' };
    const { host } = makeHost(held, () => fresh(PACKET));
    host.card = vi.fn(async () => card);
    host.lorebook = async () => [];
    const adapter = createAdapter(host);
    const send = (system: string) => adapter.beforeRequest([{ role: 'system', content: system },
      { role: 'user', content: message[0]!.data }], 'model');
    await send(`${card.desc}\n${card.personality}`); // the card is read (first sight)
    await new Promise((r) => setTimeout(r, 0));
    await send(`${card.desc}\n${card.personality}`);
    const reads = (host.card as any).mock.calls.length;
    await send(`${card.desc}\n밝고 다정하다.`); // the personality was edited in the host
    expect((host.card as any).mock.calls.length).toBe(reads + 1);
    await send(`${card.desc}\n밝고 다정하다.`); // still not held, but no longer newly missing: no read for it
    expect((host.card as any).mock.calls.length).toBe(reads + 1);
  });
});
