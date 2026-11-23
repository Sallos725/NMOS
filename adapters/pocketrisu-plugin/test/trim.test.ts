import { describe, expect, it } from 'vitest';
import { estimateTokens } from '../src/budget';
import { MEMORY_MARKER } from '../src/placement';
import { trimPrompt } from '../src/trim';
import type { HostMessage, PromptMessage } from '../src/types';

function runTrim(prompt: PromptMessage[], hostMessages: HostMessage[], keepFromId: string) {
  const promptBefore = structuredClone(prompt);
  const hostBefore = structuredClone(hostMessages);
  const res = trimPrompt(prompt, hostMessages, keepFromId);
  expect(prompt).toEqual(promptBefore);
  expect(hostMessages).toEqual(hostBefore);
  return res;
}

function toPromptRole(role: HostMessage['role']): 'user' | 'assistant' {
  return role === 'user' ? 'user' : 'assistant';
}

function buildSyntheticChat(turns: number): { host: HostMessage[]; prompt: PromptMessage[] } {
  const host: HostMessage[] = [];
  for (let n = 0; n < turns; n += 1) {
    const userText = n % 5 === 0
      ? '응'
      : `세라 walked past lamp ${n} near the harbor archive and asked 카이토 about note ${n}.`;
    const charText = n % 7 === 0
      ? '…그래.'
      : `카이토 answered 세라 beside gate ${n} while 하나 recorded entry ${n} in the ledger.`;
    host.push({ role: 'user', data: userText, chatId: `u${n}` });
    host.push({ role: 'char', data: charText, chatId: `c${n}` });
  }
  const latestUserText = turns % 5 === 0
    ? '응'
    : `유나 stepped onto the pier at turn ${turns} and asked 세라 where the bronze lantern went.`;
  host.push({ role: 'user', data: latestUserText, chatId: `u${turns}` });

  const prompt: PromptMessage[] = [
    { role: 'system', content: 'You are the narrator for 세라 and 카이토.' },
    ...host.map((m) => ({ role: toPromptRole(m.role), content: m.data })),
  ];
  return { host, prompt };
}

function baseFixture(): { host: HostMessage[]; prompt: PromptMessage[] } {
  const host: HostMessage[] = [
    { role: 'user', data: '세라 found the silver key under the stone bench in the courtyard.', chatId: 'u0' },
    { role: 'char', data: '카이토 examined the engraving on the silver key by lantern light.', chatId: 'c0' },
    { role: 'user', data: '하나 brought the ledger from the harbor warehouse before midnight.', chatId: 'u1' },
    { role: 'char', data: '유나 compared the harbor ledger with the old watchtower manifest.', chatId: 'c1' },
    { role: 'user', data: '세라 asked whether the north gate bell still rings at dawn.', chatId: 'u2' },
  ];
  const prompt: PromptMessage[] = [
    { role: 'system', content: 'System preset for the harbor story.' },
    ...host.map((m) => ({ role: toPromptRole(m.role), content: m.data })),
  ];
  return { host, prompt };
}

describe('trimPrompt (Phase 60 S1 / A15)', () => {
  it('trims a growing chat (N = 30..70) in steps of 10 with a stable prefix inside each step', () => {
    const keep = 10;
    const step = 10;
    const firstTwoByStep = new Map<number, PromptMessage[]>();

    for (let n = 30; n <= 70; n += 1) {
      const cut = Math.floor((n - keep) / step) * step;
      expect(cut).toBeGreaterThan(0);

      const { host, prompt } = buildSyntheticChat(n);
      const keepFromId = `u${cut}`;
      const res = runTrim(prompt, host, keepFromId);

      expect(res.reason).toBeNull();
      expect(res.prompt).not.toBe(prompt);
      expect(res.dropped).toBe(2 * cut);

      const expectedContents = [
        prompt[0]?.content,
        ...host.slice(2 * cut).map((m) => m.data),
      ];
      expect(res.prompt.map((m) => m.content)).toEqual(expectedContents);

      const expectedSaved = prompt
        .slice(1, 1 + 2 * cut)
        .reduce((sum, m) => sum + estimateTokens(m.content as string), 0);
      expect(res.savedTokens).toBe(expectedSaved);

      const prefix = res.prompt.slice(0, 2);
      const prev = firstTwoByStep.get(cut);
      if (prev === undefined) {
        firstTwoByStep.set(cut, prefix);
      } else {
        expect(prefix).toEqual(prev);
      }
    }
  });

  it('keeps keep_from_id when it is a short message and drops short messages right before it', () => {
    const host: HostMessage[] = [
      { role: 'user', data: '세라 opened the heavy wooden doors of the old archive.', chatId: 'u0' },
      { role: 'char', data: '…그래.', chatId: 'c0' },
      { role: 'user', data: '잠깐.', chatId: 'u1' },
      { role: 'user', data: '응', chatId: 'u2' },
      { role: 'char', data: '카이토 checked the clocktower stairs and reported back calmly.', chatId: 'c2' },
      { role: 'user', data: '하나 asked where 유나 left the copper lantern last night.', chatId: 'u3' },
    ];
    const prompt: PromptMessage[] = [
      { role: 'system', content: 'Narrator.' },
      ...host.map((m) => ({ role: toPromptRole(m.role), content: m.data })),
    ];

    const res = runTrim(prompt, host, 'u2');
    expect(res.reason).toBeNull();
    expect(res.dropped).toBe(3);
    expect(res.prompt.map((m) => m.content)).toEqual([
      'Narrator.',
      '응',
      '카이토 checked the clocktower stairs and reported back calmly.',
      '하나 asked where 유나 left the copper lantern last night.',
    ]);
  });

  it('drops short messages that sit inside the dropped run', () => {
    const host: HostMessage[] = [
      { role: 'user', data: '세라 placed the folded map onto the wooden archive table.', chatId: 'u0' },
      { role: 'char', data: '응', chatId: 'c0' },
      { role: 'user', data: '…그래.', chatId: 'u1' },
      { role: 'char', data: '카이토 traced the river road from the harbor to the tower.', chatId: 'c1' },
      { role: 'user', data: '하나 arrived carrying two warm lanterns from the guard post.', chatId: 'u2' },
      { role: 'char', data: '유나 closed the shutters before the rain reached the sill.', chatId: 'c2' },
      { role: 'user', data: '세라 asked who still holds the second key to the cellar.', chatId: 'u3' },
    ];
    const prompt: PromptMessage[] = [
      { role: 'system', content: 'Narrator.' },
      ...host.map((m) => ({ role: toPromptRole(m.role), content: m.data })),
    ];

    const res = runTrim(prompt, host, 'u2');
    expect(res.reason).toBeNull();
    expect(res.dropped).toBe(4);
    expect(res.prompt.map((m) => m.content)).toEqual([
      'Narrator.',
      '하나 arrived carrying two warm lanterns from the guard post.',
      '유나 closed the shutters before the rain reached the sill.',
      '세라 asked who still holds the second key to the cellar.',
    ]);
  });

  it('never drops the latest user turn or anything after it', () => {
    const { host, prompt } = baseFixture();

    const atLatestUser = runTrim(prompt, host, 'u2');
    expect(atLatestUser.reason).toBeNull();
    expect(atLatestUser.dropped).toBe(4);
    expect(atLatestUser.prompt.map((m) => m.content)).toEqual([
      'System preset for the harbor story.',
      '세라 asked whether the north gate bell still rings at dawn.',
    ]);

    const hostWithTrailingChar: HostMessage[] = [
      ...host,
      { role: 'char', data: '카이토 listened to the distant harbor bell echoing over the mist.', chatId: 'c2' },
    ];
    const promptWithTrailingChar: PromptMessage[] = [
      ...prompt,
      { role: 'assistant', content: '카이토 listened to the distant harbor bell echoing over the mist.' },
    ];
    const afterLatestUser = runTrim(promptWithTrailingChar, hostWithTrailingChar, 'c2');
    expect(afterLatestUser.reason).toBe('format');
    expect(afterLatestUser.dropped).toBe(0);
    expect(afterLatestUser.savedTokens).toBe(0);
    expect(afterLatestUser.prompt).toBe(promptWithTrailingChar);
  });

  it('refuses with format when a preset merges the chat into one user message', () => {
    const { host } = baseFixture();
    const mergedAll: PromptMessage[] = [
      { role: 'system', content: 'System preset.' },
      {
        role: 'user',
        content: host.map((m) => `${m.role === 'user' ? 'User' : 'Char'}: ${m.data}`).join('\n'),
      },
    ];
    const resAll = runTrim(mergedAll, host, 'u1');
    expect(resAll).toEqual({ prompt: mergedAll, dropped: 0, savedTokens: 0, reason: 'format' });
    expect(resAll.prompt).toBe(mergedAll);

    // Also when older turns are merged into a single pre-boundary user block before the latest user turn.
    const mergedPrefix: PromptMessage[] = [
      { role: 'system', content: 'System preset.' },
      {
        role: 'user',
        content: host.slice(0, 4).map((m) => `${m.role === 'user' ? 'User' : 'Char'}: ${m.data}`).join('\n'),
      },
      { role: 'user', content: host[4]!.data },
    ];
    const resPrefix = runTrim(mergedPrefix, host, 'u2');
    expect(resPrefix).toEqual({ prompt: mergedPrefix, dropped: 0, savedTokens: 0, reason: 'format' });
    expect(resPrefix.prompt).toBe(mergedPrefix);
  });

  it('refuses with format when a chat message in the run has role system', () => {
    const { host, prompt } = baseFixture();
    prompt[2] = { role: 'system', content: host[1]!.data };

    const res = runTrim(prompt, host, 'u1');
    expect(res).toEqual({ prompt, dropped: 0, savedTokens: 0, reason: 'format' });
    expect(res.prompt).toBe(prompt);
  });

  it('refuses with format when a preset note is inserted between two pre-boundary chat messages', () => {
    const { host, prompt } = baseFixture();
    prompt.splice(2, 0, { role: 'system', content: 'Author note inserted mid-history.' });

    const res = runTrim(prompt, host, 'u1');
    expect(res).toEqual({ prompt, dropped: 0, savedTokens: 0, reason: 'format' });
    expect(res.prompt).toBe(prompt);
  });

  it('refuses with format when a pre-boundary message is reshaped and older matched messages sit behind it', () => {
    const { host, prompt } = baseFixture();
    // u0 (prompt[1]) still matches, c0 (prompt[2]) is reshaped beyond recognition, u1 (prompt[3]) matches, b = c1.
    prompt[2] = { role: 'assistant', content: '[Summary substituted by an output script]' };

    const res = runTrim(prompt, host, 'c1');
    expect(res).toEqual({ prompt, dropped: 0, savedTokens: 0, reason: 'format' });
    expect(res.prompt).toBe(prompt);
  });

  it('refuses with format for multipart content or [NMOS.memory] inside the run', () => {
    const { host, prompt } = baseFixture();
    const multipartPrompt: PromptMessage[] = prompt.map((m, idx) => (idx === 2
      ? {
          role: 'assistant',
          content: [
            { type: 'text', text: host[1]!.data },
            { type: 'image_url', image_url: { url: 'https://example.invalid/harbor.png' } },
          ],
        }
      : { ...m }));
    const resMulti = runTrim(multipartPrompt, host, 'u1');
    expect(resMulti).toEqual({ prompt: multipartPrompt, dropped: 0, savedTokens: 0, reason: 'format' });
    expect(resMulti.prompt).toBe(multipartPrompt);

    const markerPrompt: PromptMessage[] = prompt.map((m, idx) => (idx === 1
      ? { role: 'user', content: `${MEMORY_MARKER}\n${host[0]!.data}` }
      : { ...m }));
    const resMarker = runTrim(markerPrompt, host, 'u1');
    expect(resMarker).toEqual({ prompt: markerPrompt, dropped: 0, savedTokens: 0, reason: 'format' });
    expect(resMarker.prompt).toBe(markerPrompt);
  });

  it('refuses with format when a message to drop carries anything beyond role and content', () => {
    const { host, prompt } = baseFixture();
    const sideFields: Array<[number, string, unknown]> = [
      [1, 'multimodals', [{ type: 'image', base64: 'data:image/png;base64,AAAA' }]],
      [2, 'tool_calls', [{ id: 'call-1', function: { name: 'lookup', arguments: '{}' } }]],
      [1, 'name', '세라'],
      [2, 'extra', undefined],
    ];
    for (const [idx, key, value] of sideFields) {
      const withField: PromptMessage[] = prompt.map((m, i) => (i === idx ? { ...m, [key]: value } : { ...m }));
      const res = runTrim(withField, host, 'u1');
      expect(res, key).toEqual({ prompt: withField, dropped: 0, savedTokens: 0, reason: 'format' });
      expect(res.prompt, key).toBe(withField);
    }

    // A kept message (the boundary and after) may carry other keys: only dropped messages are checked.
    const keptField: PromptMessage[] = prompt.map((m, i) => (i === 3
      ? { ...m, multimodals: [{ type: 'image', base64: 'data:image/png;base64,AAAA' }] }
      : { ...m }));
    const resKept = runTrim(keptField, host, 'u1');
    expect(resKept.reason).toBeNull();
    expect(resKept.dropped).toBe(2);
    expect(resKept.prompt[1]).toBe(keptField[3]);
  });

  it('refuses with format when keep_from_id is unknown or inactive', () => {
    const { host, prompt } = baseFixture();

    const unknown = runTrim(prompt, host, 'missing-id');
    expect(unknown).toEqual({ prompt, dropped: 0, savedTokens: 0, reason: 'format' });
    expect(unknown.prompt).toBe(prompt);

    const disabledHost: HostMessage[] = host.map((m) => (m.chatId === 'u1' ? { ...m, disabled: true } : { ...m }));
    const disabled = runTrim(prompt, disabledHost, 'u1');
    expect(disabled).toEqual({ prompt, dropped: 0, savedTokens: 0, reason: 'format' });
    expect(disabled.prompt).toBe(prompt);

    const commentHost: HostMessage[] = host.map((m) => (m.chatId === 'u1' ? { ...m, isComment: true } : { ...m }));
    const comment = runTrim(prompt, commentHost, 'u1');
    expect(comment).toEqual({ prompt, dropped: 0, savedTokens: 0, reason: 'format' });
    expect(comment.prompt).toBe(prompt);
  });

  it('refuses with format when a wrapped prompt message exceeds 1.25 * own + 64 characters', () => {
    const { host, prompt } = baseFixture();
    const own = host[0]!.data;
    const limit = Math.floor(1.25 * own.length + 64);

    // Just above the allowance: refused.
    const extraTooLong = 'x'.repeat(limit - own.length + 1);
    const overPrompt: PromptMessage[] = prompt.map((m, idx) => (idx === 1
      ? { role: 'user', content: `${own} ${extraTooLong}` }
      : { ...m }));
    const resOver = runTrim(overPrompt, host, 'u1');
    expect(resOver).toEqual({ prompt: overPrompt, dropped: 0, savedTokens: 0, reason: 'format' });
    expect(resOver.prompt).toBe(overPrompt);

    // Small wrapper within the allowance: accepted.
    const smallWrapPrompt: PromptMessage[] = prompt.map((m, idx) => (idx === 1
      ? { role: 'user', content: `[세라] ${own}` }
      : { ...m }));
    const resOk = runTrim(smallWrapPrompt, host, 'u1');
    expect(resOk.reason).toBeNull();
    expect(resOk.dropped).toBe(2);
  });

  it('computes savedTokens as the exact sum of estimateTokens over dropped contents', () => {
    const { host, prompt } = baseFixture();
    const res = runTrim(prompt, host, 'u1');
    expect(res.reason).toBeNull();
    expect(res.dropped).toBe(2);
    expect(res.savedTokens).toBe(
      estimateTokens(prompt[1]!.content as string) + estimateTokens(prompt[2]!.content as string),
    );
  });

  it('never throws on non-array inputs, nulls, empty keepFromId, or odd content', () => {
    const { host, prompt } = baseFixture();

    const nonArrayPrompt = null as unknown as PromptMessage[];
    expect(trimPrompt(nonArrayPrompt, host, 'u1')).toEqual({
      prompt: nonArrayPrompt,
      dropped: 0,
      savedTokens: 0,
      reason: 'format',
    });

    const nonArrayHost = undefined as unknown as HostMessage[];
    const resBadHost = trimPrompt(prompt, nonArrayHost, 'u1');
    expect(resBadHost).toEqual({ prompt, dropped: 0, savedTokens: 0, reason: 'format' });
    expect(resBadHost.prompt).toBe(prompt);

    const resEmptyId = runTrim(prompt, host, '');
    expect(resEmptyId).toEqual({ prompt, dropped: 0, savedTokens: 0, reason: 'format' });
    expect(resEmptyId.prompt).toBe(prompt);

    const oddPrompt = [
      null as unknown as PromptMessage,
      { role: 'user', content: { weird: 42 } },
      ...prompt.slice(1),
    ];
    const oddHost = [null as unknown as HostMessage, ...host];
    const resOdd = trimPrompt(oddPrompt, oddHost, 'u0');
    expect(resOdd.reason).toBe('format');
    expect(resOdd.dropped).toBe(0);
    expect(resOdd.savedTokens).toBe(0);
    expect(resOdd.prompt).toBe(oddPrompt);

    const circular: Record<string, unknown> = {};
    circular.self = circular;
    const circularPrompt: PromptMessage[] = [
      { role: 'system', content: circular },
      ...prompt.slice(1),
    ];
    const resCirc = trimPrompt(circularPrompt, host, 'u1');
    expect(resCirc).toEqual({ prompt: circularPrompt, dropped: 0, savedTokens: 0, reason: 'format' });
    expect(resCirc.prompt).toBe(circularPrompt);
  });

  it('drops only the in-window pre-boundary run when the host already truncated older messages', () => {
    const { host } = baseFixture();
    // Host sent only from u1 onward; keep_from_id = u2 should drop u1 and c1 and keep system + u2.
    const truncatedPrompt: PromptMessage[] = [
      { role: 'system', content: 'System preset for the harbor story.' },
      ...host.slice(2).map((m) => ({ role: toPromptRole(m.role), content: m.data })),
    ];
    const res = runTrim(truncatedPrompt, host, 'u2');
    expect(res.reason).toBeNull();
    expect(res.dropped).toBe(2);
    expect(res.prompt.map((m) => m.content)).toEqual([
      'System preset for the harbor story.',
      host[4]!.data,
    ]);
  });
});
