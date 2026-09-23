// Pure prompt-side logic: gating (D13), in-context detection (D3), idempotent injection (H2).

import { normalizeText } from './canonical';
import { selectedContent } from './manifest';
import type { HostMessage, PromptMessage } from './types';

export const PACKET_TAG = '<NarrativeMemory version="0" source="nmos">';

export function contentText(content: unknown): string {
  if (typeof content === 'string') return content;
  if (content == null) return '';
  return JSON.stringify(content);
}

const norm = (value: unknown): string => normalizeText(value).trim();

function isActive(message: HostMessage): boolean {
  return message.disabled !== true && !message.isComment;
}

export function latestUserIndex(messages: HostMessage[]): number {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const m = messages[i] as HostMessage;
    if (m.role === 'user' && isActive(m)) return i;
  }
  return -1;
}

/**
 * D13 / ADR 0001: index of the prompt message that carries the host chat's latest user message, newest
 * first, or -1. No preset layout is assumed: presets wrap the turn, add instruction blocks after it or
 * send it in a system message, so every message except the model's own (assistant) is searched.
 */
export function userTurnIndex(prompt: PromptMessage[], hostMessages: HostMessage[]): number {
  if (!Array.isArray(prompt)) return -1;
  const hostIndex = latestUserIndex(hostMessages);
  if (hostIndex < 0) return -1;
  // Cleaned-text containment instead of equality: input scripts may wrap or reshape the user turn.
  const expected = cleanText(selectedContent(hostMessages[hostIndex]));
  if (!expected) return -1;
  const anchor = anchorOf(expected, 64);
  for (let i = prompt.length - 1; i >= 0; i -= 1) {
    if (prompt[i]?.role === 'assistant') continue;
    const sent = cleanText(contentText(prompt[i]?.content));
    if (sent === expected || sent.includes(anchor)) return i;
  }
  return -1;
}

export function isMainGeneration(prompt: PromptMessage[], mode: unknown, hostMessages: HostMessage[]): boolean {
  return mode === 'model' && userTurnIndex(prompt, hostMessages) >= 0;
}

export function hasPacket(prompt: PromptMessage[]): boolean {
  return Array.isArray(prompt) && prompt.some((m) => contentText(m?.content).includes(PACKET_TAG));
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
 * Host message ids whose text is already in the outgoing prompt. PocketRisu sends a contiguous tail
 * of the chat in order, so match host messages newest→oldest against prompt messages newest→oldest
 * with a moving pointer: an older duplicate line can never claim a prompt slot a newer copy used.
 * Stops after a few anchorable misses (the start of the sent window).
 */
export function inContextIds(prompt: PromptMessage[], hostMessages: HostMessage[], minAnchor = 16, maxMisses = 3): string[] {
  const texts = prompt.map((m) => cleanText(contentText(m?.content)));
  let pointer = texts.length - 1;
  let boundary = hostMessages.length;
  let misses = 0;
  for (let i = hostMessages.length - 1; i >= 0 && pointer >= 0; i -= 1) {
    const m = hostMessages[i] as HostMessage;
    if (!isActive(m)) continue;
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
      boundary = i;
      pointer = found - 1;
      misses = 0;
    } else if (++misses >= maxMisses) {
      break;
    }
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
    out.push(message);
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
