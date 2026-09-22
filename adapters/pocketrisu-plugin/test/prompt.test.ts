import { describe, expect, it } from 'vitest';
import { hasPacket, inContextIds, injectPacket, isMainGeneration, PACKET_TAG, queryTexts } from '../src/prompt';
import type { HostMessage, PromptMessage } from '../src/types';

const host: HostMessage[] = [
  { role: 'user', data: 'The lantern is hidden in the old archive.', chatId: 'u0' },
  { role: 'char', data: 'I will remember where the lantern is.', chatId: 'c0' },
  { role: 'user', data: 'Tell me about the harbor bell again.', chatId: 'u1' },
  { role: 'char', data: 'The harbor bell rang twice at dusk.', chatId: 'c1' },
  { role: 'user', data: 'Where did we hide the lantern?', chatId: 'u2' },
];

const mainPrompt: PromptMessage[] = [
  { role: 'system', content: 'You are a narrator.' },
  { role: 'user', content: 'Tell me about the harbor bell again.' },
  { role: 'assistant', content: 'The harbor bell rang twice at dusk.' },
  { role: 'user', content: 'Where did we hide the lantern?' },
];

describe('gating (D13)', () => {
  it('accepts a main generation whose last user turn is the host latest user message', () => {
    expect(isMainGeneration(mainPrompt, 'model', host)).toBe(true);
  });

  it('accepts continue prompts that end with a system instruction', () => {
    expect(isMainGeneration([...mainPrompt, { role: 'system', content: 'Continue the last response.' }], 'model', host)).toBe(true);
  });

  it('rejects auxiliary modes and prompts about something else', () => {
    expect(isMainGeneration(mainPrompt, 'submodel', host)).toBe(false);
    expect(isMainGeneration([{ role: 'system', content: 'Suggest replies' }, { role: 'user', content: 'chat log…' }], 'model', host)).toBe(false);
    expect(isMainGeneration(mainPrompt, 'model', [])).toBe(false);
  });

  it('accepts a user turn reshaped by an input script', () => {
    const wrapped: PromptMessage[] = [{ role: 'user', content: '<user_input>Where did we hide the lantern?</user_input>\n(OOC: stay in character)' }];
    expect(isMainGeneration(wrapped, 'model', host)).toBe(true);
  });

  it('ignores disabled user messages when finding the latest one', () => {
    const withDisabled: HostMessage[] = [...host, { role: 'user', data: 'hidden', chatId: 'u3', disabled: true }];
    expect(isMainGeneration(mainPrompt, 'model', withDisabled)).toBe(true);
  });
});

describe('injection (H2 idempotency)', () => {
  const packet = `${PACKET_TAG}\n  <Excerpt turn="0" speaker="user">x</Excerpt>\n</NarrativeMemory>`;

  it('inserts a system message before the final user message without mutating the input', () => {
    const out = injectPacket(mainPrompt, packet);
    expect(out).not.toBe(mainPrompt);
    expect(mainPrompt).toHaveLength(4);
    expect(out.map((m) => m.role)).toEqual(['system', 'user', 'assistant', 'system', 'user']);
    expect(hasPacket(out)).toBe(true);
  });

  it('never injects twice', () => {
    const once = injectPacket(mainPrompt, packet);
    expect(injectPacket(once, packet)).toBe(once);
  });

  it('supports end placement and empty packets', () => {
    expect(injectPacket(mainPrompt, packet, 'end').at(-1)?.content).toBe(packet);
    expect(injectPacket(mainPrompt, '')).toBe(mainPrompt);
  });
});

describe('in-context detection (D3)', () => {
  it('returns the contiguous tail present in the prompt', () => {
    expect(inContextIds(mainPrompt, host)).toEqual(['u1', 'c1', 'u2']);
  });

  it('does not let older duplicate lines extend the window', () => {
    const repeated: HostMessage[] = [
      { role: 'char', data: 'She nods and looks out of the window.', chatId: 'old-dup' },
      { role: 'user', data: 'A unique early fact about the silver key.', chatId: 'fact' },
      { role: 'char', data: 'She nods and looks out of the window.', chatId: 'new-dup' },
      { role: 'user', data: 'What did we talk about earlier today?', chatId: 'last' },
    ];
    const sent: PromptMessage[] = [
      { role: 'system', content: 'narrator' },
      { role: 'assistant', content: 'She nods and looks out of the window.' },
      { role: 'user', content: 'What did we talk about earlier today?' },
    ];
    expect(inContextIds(sent, repeated)).toEqual(['new-dup', 'last']);
  });

  it('matches messages that host scripts reshaped (status HTML stripped, prefix added)', () => {
    const shaped: HostMessage[] = [
      { role: 'char', data: '<div class="st">HP 30</div>The rain did not stop all night long, and she waited.', chatId: 'c1' },
      { role: 'user', data: 'Then we walked to the harbor together at dawn.', chatId: 'u1' },
    ];
    const sent: PromptMessage[] = [
      { role: 'assistant', content: '[Narrator] The rain did not stop all night long, and she waited.' },
      { role: 'user', content: 'Then we walked to the harbor together at dawn.' },
    ];
    expect(inContextIds(sent, shaped)).toEqual(['c1', 'u1']);
  });

  it('returns nothing when the prompt shares no text', () => {
    expect(inContextIds([{ role: 'user', content: 'unrelated' }], host)).toEqual([]);
  });
});

describe('query texts', () => {
  it('uses the latest user message and the AI message before it', () => {
    expect(queryTexts(host)).toEqual({ query: 'Where did we hide the lantern?', previousAi: 'The harbor bell rang twice at dusk.' });
  });
});
