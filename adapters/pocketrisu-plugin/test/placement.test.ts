import { describe, expect, it } from 'vitest';
import {
  findMarker,
  holdsText,
  MEMORY_MARKER,
  resolvePlaceholders,
  stripMarkers,
} from '../src/placement';
import { PACKET_TAG } from '../src/prompt';
import type { PromptMessage } from '../src/types';

const samplePacket = `${PACKET_TAG}\n  <Fact subject="세라" predicate="holds">silver key</Fact>\n</NarrativeMemory>`;

describe('placement marker helpers (Phase 60 S2.3)', () => {
  it('exposes the literal marker', () => {
    expect(MEMORY_MARKER).toBe('[NMOS.memory]');
  });

  it('finds the first marker with exact message index, part index, and offset', () => {
    const inString: PromptMessage[] = [
      { role: 'system', content: 'Intro' },
      { role: 'user', content: `Hello 세라, ${MEMORY_MARKER} and ${MEMORY_MARKER}` },
      { role: 'assistant', content: MEMORY_MARKER },
    ];
    expect(findMarker(inString)).toEqual({
      message: 1,
      part: null,
      offset: 'Hello 세라, '.length,
    });

    const inMultipart: PromptMessage[] = [
      { role: 'system', content: 'System prompt' },
      {
        role: 'user',
        content: [
          { type: 'text', text: 'First text part without marker' },
          { type: 'image_url', image_url: { url: 'data:image/png;base64,AAA' } },
          { type: 'text', text: `Prefix ${MEMORY_MARKER} suffix` },
        ],
      },
    ];
    expect(findMarker(inMultipart)).toEqual({
      message: 1,
      part: 2,
      offset: 'Prefix '.length,
    });

    expect(findMarker([{ role: 'user', content: 'No marker here' }])).toBeNull();
  });

  it('replaces a marker in system, user, and assistant messages', () => {
    for (const role of ['system', 'user', 'assistant']) {
      const prompt: PromptMessage[] = [
        { role, content: `Before\n${MEMORY_MARKER}\nAfter` },
      ];
      const snapshot = structuredClone(prompt);
      const out = resolvePlaceholders(prompt, samplePacket);
      expect(out).toEqual([{ role, content: `Before\n${samplePacket}\nAfter` }]);
      expect(prompt).toEqual(snapshot);
    }
  });

  it('replaces a marker in a multipart user message second text part beside an image part without mutating unchanged parts', () => {
    const firstText = { type: 'text', text: '카이토 looks at the map.' };
    const imagePart = { type: 'image_url', image_url: { url: 'https://example.invalid/map.png' } };
    const secondText = { type: 'text', text: `Notes:\n${MEMORY_MARKER}\nEnd.`, cache_control: { type: 'ephemeral' } };
    const unchangedMsg: PromptMessage = { role: 'system', content: 'Narrator' };
    const targetMsg: PromptMessage = { role: 'user', name: '카이토', content: [firstText, imagePart, secondText] };
    const prompt: PromptMessage[] = [unchangedMsg, targetMsg];
    const snapshot = structuredClone(prompt);

    const out = resolvePlaceholders(prompt, samplePacket);

    expect(prompt).toEqual(snapshot);
    expect(out).not.toBe(prompt);
    expect(out[0]).toBe(unchangedMsg);
    expect(out[1]).not.toBe(targetMsg);
    expect(out[1]?.name).toBe('카이토');

    const outParts = out[1]?.content as unknown[];
    expect(outParts[0]).toBe(firstText);
    expect(outParts[1]).toBe(imagePart);
    expect(outParts[2]).not.toBe(secondText);
    expect(outParts[2]).toEqual({
      type: 'text',
      text: `Notes:\n${samplePacket}\nEnd.`,
      cache_control: { type: 'ephemeral' },
    });
  });

  it('replaces the first marker and removes the second inside one string', () => {
    const prompt: PromptMessage[] = [
      { role: 'user', content: `A ${MEMORY_MARKER} B ${MEMORY_MARKER} C` },
    ];
    const out = resolvePlaceholders(prompt, samplePacket);
    expect(out[0]?.content).toBe(`A ${samplePacket} B  C`);
    expect(findMarker(out)).toBeNull();
  });

  it('places the packet only at the first marker across three messages and removes the rest', () => {
    const keep: PromptMessage = { role: 'system', content: 'Static header' };
    const prompt: PromptMessage[] = [
      keep,
      { role: 'system', content: `First: ${MEMORY_MARKER}` },
      { role: 'user', content: [{ type: 'text', text: `Second: ${MEMORY_MARKER}` }] },
      { role: 'assistant', content: `Third: ${MEMORY_MARKER}` },
    ];
    const snapshot = structuredClone(prompt);

    const out = resolvePlaceholders(prompt, samplePacket);

    expect(prompt).toEqual(snapshot);
    expect(out[0]).toBe(keep);
    expect(out[1]?.content).toBe(`First: ${samplePacket}`);
    expect(out[2]?.content).toEqual([{ type: 'text', text: 'Second: ' }]);
    expect(out[3]?.content).toBe('Third: ');
    expect(findMarker(out)).toBeNull();
  });

  it('removes all markers when packet is empty or via stripMarkers, keeping empty messages in place', () => {
    const prompt: PromptMessage[] = [
      { role: 'system', content: MEMORY_MARKER },
      { role: 'user', content: [{ type: 'text', text: MEMORY_MARKER }] },
      { role: 'assistant', content: `하나 says ${MEMORY_MARKER}` },
    ];
    const snapshot = structuredClone(prompt);

    const outEmpty = resolvePlaceholders(prompt, '');
    const outStripped = stripMarkers(prompt);

    expect(prompt).toEqual(snapshot);
    expect(outEmpty).toHaveLength(3);
    expect(outEmpty[0]).toEqual({ role: 'system', content: '' });
    expect(outEmpty[1]).toEqual({ role: 'user', content: [{ type: 'text', text: '' }] });
    expect(outEmpty[2]).toEqual({ role: 'assistant', content: '하나 says ' });
    expect(outStripped).toEqual(outEmpty);
    expect(findMarker(outEmpty)).toBeNull();
  });

  it('strips any literal marker inside the packet itself and never rescans the inserted packet', () => {
    const trickyPacket = `${PACKET_TAG}\n  <Excerpt>유나 wrote ${MEMORY_MARKER} ($& $$) in the margin</Excerpt>\n</NarrativeMemory>`;
    const prompt: PromptMessage[] = [
      { role: 'system', content: `Here: ${MEMORY_MARKER}` },
      { role: 'user', content: `Also: ${MEMORY_MARKER}` },
    ];

    const out = resolvePlaceholders(prompt, trickyPacket);
    const expectedClean = `${PACKET_TAG}\n  <Excerpt>유나 wrote  ($& $$) in the margin</Excerpt>\n</NarrativeMemory>`;

    expect(out[0]?.content).toBe(`Here: ${expectedClean}`);
    expect(out[1]?.content).toBe('Also: ');
    expect(findMarker(out)).toBeNull();
  });

  it('returns the exact same array reference when no marker is present', () => {
    const prompt: PromptMessage[] = [
      { role: 'system', content: 'Narrator' },
      { role: 'user', content: [{ type: 'text', text: 'Hello' }, { type: 'image_url', url: 'x' }] },
    ];
    expect(resolvePlaceholders(prompt, samplePacket)).toBe(prompt);
    expect(stripMarkers(prompt)).toBe(prompt);
  });

  it('is total and leaves malformed prompts, entries, contents, and parts untouched', () => {
    const notAnArray = { role: 'user', content: MEMORY_MARKER } as unknown as PromptMessage[];
    expect(resolvePlaceholders(notAnArray, samplePacket)).toBe(notAnArray);
    expect(stripMarkers(notAnArray)).toBe(notAnArray);
    expect(findMarker(notAnArray)).toBeNull();
    expect(findMarker(null)).toBeNull();
    expect(findMarker(undefined)).toBeNull();

    const weirdObjContent = { text: MEMORY_MARKER };
    const weirdParts = [null, undefined, `raw ${MEMORY_MARKER}`, 42, { type: 'image', text: MEMORY_MARKER }, { type: 'text', text: 123 }];
    const weirdPrompt = [
      null,
      undefined,
      { role: 'system' },
      { role: 'user', content: 12345 },
      { role: 'user', content: weirdObjContent },
      { role: 'user', content: weirdParts },
      { role: 'assistant', content: `Valid ${MEMORY_MARKER}` },
    ] as unknown as PromptMessage[];

    expect(findMarker(weirdPrompt)).toEqual({ message: 6, part: null, offset: 6 });

    const out = resolvePlaceholders(weirdPrompt, samplePacket);
    expect(out[0]).toBeNull();
    expect(out[1]).toBeUndefined();
    expect(out[2]).toBe(weirdPrompt[2]);
    expect(out[3]).toBe(weirdPrompt[3]);
    expect(out[4]).toBe(weirdPrompt[4]);
    expect(out[5]).toBe(weirdPrompt[5]);
    expect(out[6]?.content).toBe(`Valid ${samplePacket}`);

    const mixedMultipart = [
      {
        role: 'user',
        content: [null, 'raw string', { type: 'text', text: `Hit ${MEMORY_MARKER}` }],
      },
    ] as unknown as PromptMessage[];
    const outMixed = resolvePlaceholders(mixedMultipart, 'PKT');
    expect((outMixed[0]?.content as unknown[])[0]).toBeNull();
    expect((outMixed[0]?.content as unknown[])[1]).toBe('raw string');
    expect((outMixed[0]?.content as unknown[])[2]).toEqual({ type: 'text', text: 'Hit PKT' });
  });

  it('detects raw text in string content and multipart text parts via holdsText', () => {
    const packetWithQuotesAndNewlines = `${PACKET_TAG}\n  <Excerpt speaker="세라">"Don't forget."</Excerpt>\n</NarrativeMemory>`;
    const prompt: PromptMessage[] = [
      { role: 'system', content: 'Intro' },
      {
        role: 'user',
        content: [
          { type: 'image_url', image_url: { url: 'x' } },
          { type: 'text', text: `Prefix\n${packetWithQuotesAndNewlines}\nSuffix` },
        ],
      },
    ];

    expect(holdsText(prompt, packetWithQuotesAndNewlines)).toBe(true);
    expect(holdsText([{ role: 'assistant', content: packetWithQuotesAndNewlines }], packetWithQuotesAndNewlines)).toBe(true);
    expect(holdsText(prompt, '')).toBe(false);
    expect(holdsText(prompt, 'not present')).toBe(false);
    expect(holdsText(null, 'Intro')).toBe(false);
    expect(holdsText([{ role: 'user', content: [null, 'Intro', { type: 'image', text: 'Intro' }] }], 'Intro')).toBe(false);
  });
});
