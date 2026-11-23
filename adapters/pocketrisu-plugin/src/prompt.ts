// Pure prompt-side logic: gating (D13), in-context detection (D3), idempotent injection (H2).

import { normalizeText } from './canonical';
import { selectedContent } from './manifest';
import { isTextPart, MEMORY_MARKER, type MarkerAt } from './placement';
import type { HostMessage, PromptMessage } from './types';

export const PACKET_TAG = '<NarrativeMemory version="0" source="nmos">';
export const GUARD_LINE = "(The user's most recent message comes before this memory and has already happened; where the two differ, that message wins.)";
export const GUARD_RESERVE_TOKENS = 40;

export function contentText(content: unknown): string {
  if (typeof content === 'string') return content;
  if (content == null) return '';
  return JSON.stringify(content);
}

const norm = (value: unknown): string => normalizeText(value).trim();

export function isActive(message: HostMessage | null | undefined): boolean {
  return message != null && message.disabled !== true && !message.isComment;
}

export function latestUserIndex(messages: HostMessage[]): number {
  if (!Array.isArray(messages)) return -1;
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const m = messages[i];
    if (m && m.role === 'user' && isActive(m)) return i;
  }
  return -1;
}

/** Cleaned middle-64 anchor of the latest active user host message, or empty string when none. */
export function userTurnAnchor(hostMessages: HostMessage[]): string {
  if (!Array.isArray(hostMessages)) return '';
  const hostIndex = latestUserIndex(hostMessages);
  if (hostIndex < 0) return '';
  const expected = cleanText(selectedContent(hostMessages[hostIndex]));
  return expected ? anchorOf(expected, 64) : '';
}

/**
 * D13 / ADR 0001: index of the prompt message that carries the host chat's latest user message, newest
 * first, or -1. No preset layout is assumed: presets wrap the turn, add instruction blocks after it or
 * send it in a system message, so every message except the model's own (assistant) is searched.
 */
export function userTurnIndex(prompt: PromptMessage[], hostMessages: HostMessage[]): number {
  if (!Array.isArray(prompt)) return -1;
  const anchor = userTurnAnchor(hostMessages);
  if (!anchor) return -1;
  // Cleaned-text containment instead of equality: input scripts may wrap or reshape the user turn.
  for (let i = prompt.length - 1; i >= 0; i -= 1) {
    if (prompt[i]?.role === 'assistant') continue;
    const sent = cleanText(contentText(prompt[i]?.content));
    if (sent.includes(anchor)) return i;
  }
  return -1;
}

export function isMainGeneration(prompt: PromptMessage[], mode: unknown, hostMessages: HostMessage[]): boolean {
  return mode === 'model' && userTurnIndex(prompt, hostMessages) >= 0;
}

/** Only a system message can be our packet: a reply or user message quoting the tag must not stop memory. */
export function hasPacket(prompt: PromptMessage[]): boolean {
  return Array.isArray(prompt)
    && prompt.some((m) => m?.role === 'system' && contentText(m.content).includes(PACKET_TAG));
}

/** Visible text only: host regex scripts and status HTML often reshape what is sent to the model. */
export function cleanText(value: unknown): string {
  return normalizeText(value)
    .replace(/<(style|script)\b[^>]*>[\s\S]*?<\/\1\s*>/gi, ' ')
    .replace(/<[^>\n]{1,500}>/g, ' ')
    .replace(/&nbsp;/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

/** A distinctive slice from the middle of a message: survives prefixes/suffixes added or removed by scripts. */
export function anchorOf(text: string, size = 48): string {
  if (text.length <= size) return text;
  const start = Math.floor((text.length - size) / 2);
  return text.slice(start, start + size);
}

/**
 * Pointer-matches active, anchorable host messages newest→oldest against outgoing prompt messages
 * newest→oldest, returning a map of host index → prompt index. An older duplicate line can never
 * claim a prompt slot a newer copy used; stops after `maxMisses` consecutive anchorable misses.
 */
export function matchPromptToHost(
  prompt: PromptMessage[],
  hostMessages: HostMessage[],
  minAnchor = 16,
  maxMisses = 3,
): Map<number, number> {
  const matches = new Map<number, number>();
  if (!Array.isArray(prompt) || !Array.isArray(hostMessages)) return matches;
  const texts = prompt.map((m) => cleanText(contentText(m?.content)));
  let pointer = texts.length - 1;
  let misses = 0;
  for (let i = hostMessages.length - 1; i >= 0 && pointer >= 0; i -= 1) {
    const m = hostMessages[i];
    if (!m || !isActive(m)) continue;
    const text = cleanText(selectedContent(m));
    if (text.length < minAnchor) continue;
    const anchor = anchorOf(text);
    let found = -1;
    for (let k = pointer; k >= 0; k -= 1) {
      if ((texts[k] as string).includes(anchor)) {
        found = k;
        break;
      }
    }
    if (found >= 0) {
      matches.set(i, found);
      pointer = found - 1;
      misses = 0;
    } else if (++misses >= maxMisses) {
      break;
    }
  }
  return matches;
}

/**
 * Host message ids whose text is already in the outgoing prompt. PocketRisu sends a contiguous tail
 * of the chat in order, so `matchPromptToHost` finds the smallest matched host index and every
 * message from there to the end of `hostMessages` is reported as in context.
 */
export function inContextIds(prompt: PromptMessage[], hostMessages: HostMessage[], minAnchor = 16, maxMisses = 3): string[] {
  const matches = matchPromptToHost(prompt, hostMessages, minAnchor, maxMisses);
  if (matches.size === 0) return [];
  let boundary = hostMessages.length;
  for (const i of matches.keys()) {
    if (i < boundary) boundary = i;
  }
  return hostMessages.slice(boundary).map((m) => String(m.chatId ?? '')).filter(Boolean);
}

export type InjectPosition = 'before_last_user' | 'end';

/**
 * Returns a new prompt array with the packet as a system message; never mutates the input.
 * `before_last_user` places it before the user turn (`turn`, from userTurnIndex), or before the last
 * user message when the turn is unknown. A preset may split the turn over several user messages (an
 * opening wrapper, then the text), so the packet goes before the whole run of user messages.
 */
export function injectPacket(prompt: PromptMessage[], packet: string, position: InjectPosition = 'before_last_user',
                             turn = -1): PromptMessage[] {
  if (!packet || hasPacket(prompt)) return prompt;
  const message: PromptMessage = { role: 'system', content: packet };
  const out = prompt.slice();
  if (position === 'end') {
    let index = out.length;
    while (index > 0 && out[index - 1]?.role === 'assistant') index -= 1;
    out.splice(index, 0, message);
    return out;
  }
  let index = turn >= 0 && turn < out.length && out[turn]?.role !== 'assistant' ? turn : out.length;
  for (let i = out.length - 1; index === out.length && i >= 0; i -= 1) {
    if (out[i]?.role === 'user') index = i;
  }
  while (index > 0 && out[index]?.role === 'user' && out[index - 1]?.role === 'user') index -= 1;
  out.splice(index, 0, message);
  return out;
}

/** Appends the post-turn guard line right after `</NarrativeMemory>` (empty packet stays empty). */
export function withGuard(packet: string): string {
  return packet ? `${packet}\n${GUARD_LINE}` : '';
}

function textAfterMarker(message: PromptMessage | undefined, marker: MarkerAt): string {
  const content = message?.content;
  const start = marker.offset + MEMORY_MARKER.length;
  if (marker.part === null) {
    return typeof content === 'string' ? content.slice(start) : '';
  }
  if (!Array.isArray(content)) return '';
  const chunks: string[] = [];
  const part = content[marker.part];
  if (isTextPart(part)) chunks.push(part.text.slice(start));
  for (let j = marker.part + 1; j < content.length; j += 1) {
    const later = content[j];
    if (isTextPart(later)) chunks.push(later.text);
  }
  return chunks.join('\n');
}

/**
 * True when the packet will land after the latest user turn (by `end` placement or a placeholder),
 * so the guard line applies and its token reserve is deducted from the requested budget (Phase 60 S2.2).
 */
export function landsAfterUserTurn(
  prompt: PromptMessage[],
  hostMessages: HostMessage[],
  position: InjectPosition,
  turn: number,
  marker: MarkerAt | null,
): boolean {
  if (turn < 0) return position === 'end' || marker !== null;
  if (marker === null) return position === 'end';
  if (marker.message > turn) return true;
  if (marker.message < turn) return false;
  const anchor = userTurnAnchor(hostMessages);
  if (!anchor) return true;
  const after = Array.isArray(prompt) ? textAfterMarker(prompt[marker.message], marker) : '';
  return !cleanText(after).includes(anchor);
}

/** Text of the latest active user message and of the AI message just before it. */
export function queryTexts(hostMessages: HostMessage[]): { query: string; previousAi: string } {
  const userIndex = latestUserIndex(hostMessages);
  const query = userIndex >= 0 ? normalizeText(selectedContent(hostMessages[userIndex])) : '';
  let previousAi = '';
  for (let i = userIndex - 1; i >= 0; i -= 1) {
    const m = hostMessages[i] as HostMessage;
    if (m.role === 'char' && isActive(m)) {
      previousAi = normalizeText(selectedContent(m));
      break;
    }
  }
  return { query, previousAi };
}
