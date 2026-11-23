import { describe, expect, it } from 'vitest';
import { findMarker, MEMORY_MARKER } from '../src/placement';
import {
  GUARD_LINE,
  GUARD_RESERVE_TOKENS,
  hasPacket,
  inContextIds,
  injectPacket,
  isMainGeneration,
  landsAfterUserTurn,
  PACKET_TAG,
  queryTexts,
  userTurnAnchor,
  userTurnIndex,
  withGuard,
} from '../src/prompt';
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

// Shape of a real preset (owner's HELENA, 2026-09-23): the turn is wrapped over several user messages
// and followed by user-role instruction blocks, the last one a converted system note.
const presetPrompt: PromptMessage[] = [
  { role: 'system', content: '# System Prompt' },
  { role: 'user', content: 'Tell me about the harbor bell again.' },
  { role: 'assistant', content: '<Last output>' },
  { role: 'assistant', content: 'The harbor bell rang twice at dusk.' },
  { role: 'assistant', content: '</Last output>' },
  { role: 'user', content: '<Current Input>\n\n```' },
  { role: 'user', content: 'Where did we hide the lantern?' },
  { role: 'user', content: '```\n</Current Input>\n\nTake my current input as inspiration.' },
  { role: 'user', content: '---\n\n# Feedback\n- Proactive Writer' },
  { role: 'user', content: '---\n\n# Tags' },
  { role: 'user', content: 'system: POV : Omniscient Point of View.' },
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

  it('finds the turn when a preset adds instruction blocks after it', () => {
    expect(userTurnIndex(presetPrompt, host)).toBe(6);
    expect(isMainGeneration(presetPrompt, 'model', host)).toBe(true);
  });

  it('finds the turn in a system message and never in assistant messages', () => {
    const inSystem: PromptMessage[] = [{ role: 'system', content: 'Chat log:\nUser: Where did we hide the lantern?\nReply now.' }];
    expect(userTurnIndex(inSystem, host)).toBe(0);
    const echoed: PromptMessage[] = [{ role: 'system', content: 'Narrate.' }, { role: 'assistant', content: 'Where did we hide the lantern?' }];
    expect(userTurnIndex(echoed, host)).toBe(-1);
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

  it('goes before the whole user run that holds the turn, not inside the preset wrapper', () => {
    const out = injectPacket(presetPrompt, packet, 'before_last_user', userTurnIndex(presetPrompt, host));
    expect(out[5]?.content).toBe(packet);
    expect(out[6]?.content).toBe('<Current Input>\n\n```');
    expect(out).toHaveLength(presetPrompt.length + 1);
  });

  it('does not mistake a message quoting the packet tag for an injected packet', () => {
    const quoted: PromptMessage[] = [
      ...mainPrompt.slice(0, 3),
      { role: 'assistant', content: `As the notes say: ${PACKET_TAG} …` },
      { role: 'user', content: `What is ${PACKET_TAG}?` },
    ];
    expect(hasPacket(quoted)).toBe(false);
    const out = injectPacket(quoted, packet);
    expect(out).toHaveLength(quoted.length + 1);
    expect(hasPacket(out)).toBe(true);
  });

  it('supports end placement and empty packets', () => {
    expect(injectPacket(mainPrompt, packet, 'end').at(-1)?.content).toBe(packet);
    expect(injectPacket(mainPrompt, '')).toBe(mainPrompt);
  });

  it('places end injection before a trailing run of assistant prefill messages', () => {
    const onePrefill: PromptMessage[] = [
      ...mainPrompt,
      { role: 'assistant', content: '세라 stepped forward.' },
    ];
    const outOne = injectPacket(onePrefill, packet, 'end');
    expect(outOne.map((m) => m.role)).toEqual(['system', 'user', 'assistant', 'user', 'system', 'assistant']);
    expect(outOne[4]?.content).toBe(packet);
    expect(outOne[5]?.content).toBe('세라 stepped forward.');
    expect(onePrefill).toHaveLength(5);

    const twoPrefill: PromptMessage[] = [
      ...mainPrompt,
      { role: 'assistant', content: '<thought>' },
      { role: 'assistant', content: '세라 stepped forward.' },
    ];
    const outTwo = injectPacket(twoPrefill, packet, 'end');
    expect(outTwo.map((m) => m.role)).toEqual(['system', 'user', 'assistant', 'user', 'system', 'assistant', 'assistant']);
    expect(outTwo[4]?.content).toBe(packet);
    expect(outTwo[5]?.content).toBe('<thought>');
    expect(outTwo[6]?.content).toBe('세라 stepped forward.');

    const noTrailingAssistant: PromptMessage[] = [
      ...mainPrompt,
      { role: 'assistant', content: 'Earlier reply.' },
      { role: 'system', content: 'Continue.' },
    ];
    const outNone = injectPacket(noTrailingAssistant, packet, 'end');
    expect(outNone.at(-1)?.content).toBe(packet);
    expect(outNone).toHaveLength(noTrailingAssistant.length + 1);
  });

  it('keeps before_last_user byte-identical across existing fixtures (pinned at 375efa5)', () => {
    const continuePrompt: PromptMessage[] = [...mainPrompt, { role: 'system', content: 'Continue the last response.' }];
    const wrapped: PromptMessage[] = [
      { role: 'user', content: '<user_input>Where did we hide the lantern?</user_input>\n(OOC: stay in character)' },
    ];
    const inSystem: PromptMessage[] = [
      { role: 'system', content: 'Chat log:\nUser: Where did we hide the lantern?\nReply now.' },
    ];
    const quoted: PromptMessage[] = [
      ...mainPrompt.slice(0, 3),
      { role: 'assistant', content: `As the notes say: ${PACKET_TAG} …` },
      { role: 'user', content: `What is ${PACKET_TAG}?` },
    ];

    const expectedMain = [
      { role: 'system', content: 'You are a narrator.' },
      { role: 'user', content: 'Tell me about the harbor bell again.' },
      { role: 'assistant', content: 'The harbor bell rang twice at dusk.' },
      { role: 'system', content: packet },
      { role: 'user', content: 'Where did we hide the lantern?' },
    ];
    expect(JSON.stringify(injectPacket(mainPrompt, packet, 'before_last_user', userTurnIndex(mainPrompt, host))))
      .toBe(JSON.stringify(expectedMain));
    expect(JSON.stringify(injectPacket(mainPrompt, packet, 'before_last_user', -1)))
      .toBe(JSON.stringify(expectedMain));

    const expectedPreset = [
      { role: 'system', content: '# System Prompt' },
      { role: 'user', content: 'Tell me about the harbor bell again.' },
      { role: 'assistant', content: '<Last output>' },
      { role: 'assistant', content: 'The harbor bell rang twice at dusk.' },
      { role: 'assistant', content: '</Last output>' },
      { role: 'system', content: packet },
      { role: 'user', content: '<Current Input>\n\n```' },
      { role: 'user', content: 'Where did we hide the lantern?' },
      { role: 'user', content: '```\n</Current Input>\n\nTake my current input as inspiration.' },
      { role: 'user', content: '---\n\n# Feedback\n- Proactive Writer' },
      { role: 'user', content: '---\n\n# Tags' },
      { role: 'user', content: 'system: POV : Omniscient Point of View.' },
    ];
    expect(JSON.stringify(injectPacket(presetPrompt, packet, 'before_last_user', userTurnIndex(presetPrompt, host))))
      .toBe(JSON.stringify(expectedPreset));
    expect(JSON.stringify(injectPacket(presetPrompt, packet, 'before_last_user', -1)))
      .toBe(JSON.stringify(expectedPreset));

    const expectedContinue = [
      { role: 'system', content: 'You are a narrator.' },
      { role: 'user', content: 'Tell me about the harbor bell again.' },
      { role: 'assistant', content: 'The harbor bell rang twice at dusk.' },
      { role: 'system', content: packet },
      { role: 'user', content: 'Where did we hide the lantern?' },
      { role: 'system', content: 'Continue the last response.' },
    ];
    expect(JSON.stringify(injectPacket(continuePrompt, packet, 'before_last_user', userTurnIndex(continuePrompt, host))))
      .toBe(JSON.stringify(expectedContinue));
    expect(JSON.stringify(injectPacket(continuePrompt, packet, 'before_last_user', -1)))
      .toBe(JSON.stringify(expectedContinue));

    const expectedWrapped = [
      { role: 'system', content: packet },
      { role: 'user', content: '<user_input>Where did we hide the lantern?</user_input>\n(OOC: stay in character)' },
    ];
    expect(JSON.stringify(injectPacket(wrapped, packet, 'before_last_user', userTurnIndex(wrapped, host))))
      .toBe(JSON.stringify(expectedWrapped));
    expect(JSON.stringify(injectPacket(wrapped, packet, 'before_last_user', -1)))
      .toBe(JSON.stringify(expectedWrapped));

    const expectedInSystemWithTurn = [
      { role: 'system', content: packet },
      { role: 'system', content: 'Chat log:\nUser: Where did we hide the lantern?\nReply now.' },
    ];
    const expectedInSystemNoTurn = [
      { role: 'system', content: 'Chat log:\nUser: Where did we hide the lantern?\nReply now.' },
      { role: 'system', content: packet },
    ];
    expect(JSON.stringify(injectPacket(inSystem, packet, 'before_last_user', userTurnIndex(inSystem, host))))
      .toBe(JSON.stringify(expectedInSystemWithTurn));
    expect(JSON.stringify(injectPacket(inSystem, packet, 'before_last_user', -1)))
      .toBe(JSON.stringify(expectedInSystemNoTurn));

    const expectedQuoted = [
      { role: 'system', content: 'You are a narrator.' },
      { role: 'user', content: 'Tell me about the harbor bell again.' },
      { role: 'assistant', content: 'The harbor bell rang twice at dusk.' },
      { role: 'assistant', content: `As the notes say: ${PACKET_TAG} …` },
      { role: 'system', content: packet },
      { role: 'user', content: `What is ${PACKET_TAG}?` },
    ];
    expect(JSON.stringify(injectPacket(quoted, packet, 'before_last_user', userTurnIndex(quoted, host))))
      .toBe(JSON.stringify(expectedQuoted));
    expect(JSON.stringify(injectPacket(quoted, packet, 'before_last_user', -1)))
      .toBe(JSON.stringify(expectedQuoted));
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

  it('pins inContextIds output across every fixture before matchPromptToHost refactor', () => {
    const continuePrompt: PromptMessage[] = [...mainPrompt, { role: 'system', content: 'Continue the last response.' }];
    const wrapped: PromptMessage[] = [
      { role: 'user', content: '<user_input>Where did we hide the lantern?</user_input>\n(OOC: stay in character)' },
    ];
    const inSystem: PromptMessage[] = [
      { role: 'system', content: 'Chat log:\nUser: Where did we hide the lantern?\nReply now.' },
    ];
    const echoed: PromptMessage[] = [
      { role: 'system', content: 'Narrate.' },
      { role: 'assistant', content: 'Where did we hide the lantern?' },
    ];
    const withDisabled: HostMessage[] = [
      ...host,
      { role: 'user', data: 'hidden', chatId: 'u3', disabled: true },
    ];
    const quoted: PromptMessage[] = [
      ...mainPrompt.slice(0, 3),
      { role: 'assistant', content: `As the notes say: ${PACKET_TAG} …` },
      { role: 'user', content: `What is ${PACKET_TAG}?` },
    ];
    const onePrefill: PromptMessage[] = [
      ...mainPrompt,
      { role: 'assistant', content: '세라 stepped forward.' },
    ];

    expect(inContextIds(mainPrompt, host)).toEqual(['u1', 'c1', 'u2']);
    expect(inContextIds(presetPrompt, host)).toEqual(['u1', 'c1', 'u2']);
    expect(inContextIds(continuePrompt, host)).toEqual(['u1', 'c1', 'u2']);
    expect(inContextIds(wrapped, host)).toEqual(['u2']);
    expect(inContextIds(inSystem, host)).toEqual(['u2']);
    expect(inContextIds(echoed, host)).toEqual(['u2']);
    expect(inContextIds(mainPrompt, withDisabled)).toEqual(['u1', 'c1', 'u2', 'u3']);
    expect(inContextIds(quoted, host)).toEqual(['u1', 'c1', 'u2']);
    expect(inContextIds(onePrefill, host)).toEqual(['u1', 'c1', 'u2']);
    expect(inContextIds([], host)).toEqual([]);
    expect(inContextIds(mainPrompt, [])).toEqual([]);
  });
});

describe('query texts', () => {
  it('uses the latest user message and the AI message before it', () => {
    expect(queryTexts(host)).toEqual({ query: 'Where did we hide the lantern?', previousAi: 'The harbor bell rang twice at dusk.' });
  });
});

describe('guard line and post-turn landing (Phase 60 S2.2)', () => {
  const packet = `${PACKET_TAG}\n  <Fact subject="세라">holds lantern</Fact>\n</NarrativeMemory>`;

  it('appends the guard line only to non-empty packets and exports the reserve', () => {
    expect(GUARD_RESERVE_TOKENS).toBe(40);
    expect(withGuard(packet)).toBe(`${packet}\n${GUARD_LINE}`);
    expect(withGuard('')).toBe('');
  });

  it('extracts userTurnAnchor from the latest active user message', () => {
    expect(userTurnAnchor(host)).toBe('Where did we hide the lantern?');
    expect(userTurnAnchor([])).toBe('');
    expect(userTurnAnchor([{ role: 'user', data: '<div>   </div>', chatId: 'u0' }])).toBe('');
    const longMsg = 'a'.repeat(30) + 'MIDDLE_ANCHOR_TEXT_FOR_SERA_AND_KAITO_TEST' + 'b'.repeat(30);
    const longHost: HostMessage[] = [{ role: 'user', data: longMsg, chatId: 'u0' }];
    expect(userTurnAnchor(longHost)).toHaveLength(64);
    expect(longMsg.includes(userTurnAnchor(longHost))).toBe(true);
  });

  it('decides landsAfterUserTurn when no marker is present', () => {
    const turn = userTurnIndex(mainPrompt, host);
    expect(landsAfterUserTurn(mainPrompt, host, 'end', turn, null)).toBe(true);
    expect(landsAfterUserTurn(mainPrompt, host, 'before_last_user', turn, null)).toBe(false);
  });

  it('decides landsAfterUserTurn when turn is unknown (turn < 0)', () => {
    const marker = { message: 0, part: null, offset: 0 };
    expect(landsAfterUserTurn(mainPrompt, host, 'end', -1, null)).toBe(true);
    expect(landsAfterUserTurn(mainPrompt, host, 'before_last_user', -1, null)).toBe(false);
    expect(landsAfterUserTurn(mainPrompt, host, 'before_last_user', -1, marker)).toBe(true);
    expect(landsAfterUserTurn(mainPrompt, host, 'end', -1, marker)).toBe(true);
  });

  it('decides landsAfterUserTurn by message order when marker is in a different message', () => {
    const markerBefore: PromptMessage[] = [
      { role: 'system', content: `Header\n${MEMORY_MARKER}` },
      ...mainPrompt.slice(1),
    ];
    const turnBefore = userTurnIndex(markerBefore, host);
    expect(landsAfterUserTurn(markerBefore, host, 'end', turnBefore, findMarker(markerBefore))).toBe(false);

    const markerAfter: PromptMessage[] = [
      ...mainPrompt,
      { role: 'system', content: `Trailer\n${MEMORY_MARKER}` },
    ];
    const turnAfter = userTurnIndex(markerAfter, host);
    expect(landsAfterUserTurn(markerAfter, host, 'before_last_user', turnAfter, findMarker(markerAfter))).toBe(true);
  });

  it('decides landsAfterUserTurn when marker shares the turn message (string content)', () => {
    const beforeUserText: PromptMessage[] = [
      ...mainPrompt.slice(0, 3),
      { role: 'user', content: `${MEMORY_MARKER}\nWhere did we hide the lantern?` },
    ];
    const turnA = userTurnIndex(beforeUserText, host);
    expect(landsAfterUserTurn(beforeUserText, host, 'end', turnA, findMarker(beforeUserText))).toBe(false);

    const afterUserText: PromptMessage[] = [
      ...mainPrompt.slice(0, 3),
      { role: 'user', content: `Where did we hide the lantern?\n${MEMORY_MARKER}` },
    ];
    const turnB = userTurnIndex(afterUserText, host);
    expect(landsAfterUserTurn(afterUserText, host, 'before_last_user', turnB, findMarker(afterUserText))).toBe(true);

    // Empty anchor defaults to true when marker is in the turn message.
    expect(landsAfterUserTurn(beforeUserText, [], 'before_last_user', turnA, findMarker(beforeUserText))).toBe(true);
  });

  it('decides landsAfterUserTurn when marker shares a multipart turn message', () => {
    const markerEarlierPart: PromptMessage[] = [
      ...mainPrompt.slice(0, 3),
      {
        role: 'user',
        content: [
          { type: 'text', text: `Context: ${MEMORY_MARKER}` },
          { type: 'image_url', image_url: { url: 'https://example.invalid/a.png' } },
          { type: 'text', text: 'Where did we hide the lantern?' },
        ],
      },
    ];
    const turnEarlier = userTurnIndex(markerEarlierPart, host);
    expect(landsAfterUserTurn(markerEarlierPart, host, 'end', turnEarlier, findMarker(markerEarlierPart))).toBe(false);

    const markerLaterPart: PromptMessage[] = [
      ...mainPrompt.slice(0, 3),
      {
        role: 'user',
        content: [
          { type: 'text', text: 'Where did we hide the lantern?' },
          { type: 'image_url', image_url: { url: 'https://example.invalid/a.png' } },
          { type: 'text', text: `Notes: ${MEMORY_MARKER}` },
        ],
      },
    ];
    const turnLater = userTurnIndex(markerLaterPart, host);
    expect(landsAfterUserTurn(markerLaterPart, host, 'before_last_user', turnLater, findMarker(markerLaterPart))).toBe(true);

    const markerSamePartBefore: PromptMessage[] = [
      ...mainPrompt.slice(0, 3),
      {
        role: 'user',
        content: [
          { type: 'image_url', image_url: { url: 'https://example.invalid/a.png' } },
          { type: 'text', text: `${MEMORY_MARKER} Where did we hide the lantern?` },
        ],
      },
    ];
    const turnSameBefore = userTurnIndex(markerSamePartBefore, host);
    expect(landsAfterUserTurn(markerSamePartBefore, host, 'end', turnSameBefore, findMarker(markerSamePartBefore))).toBe(false);

    const markerSamePartAfter: PromptMessage[] = [
      ...mainPrompt.slice(0, 3),
      {
        role: 'user',
        content: [
          { type: 'image_url', image_url: { url: 'https://example.invalid/a.png' } },
          { type: 'text', text: `Where did we hide the lantern? ${MEMORY_MARKER}` },
        ],
      },
    ];
    const turnSameAfter = userTurnIndex(markerSamePartAfter, host);
    expect(landsAfterUserTurn(markerSamePartAfter, host, 'before_last_user', turnSameAfter, findMarker(markerSamePartAfter))).toBe(true);
  });
});
