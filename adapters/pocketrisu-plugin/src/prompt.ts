// Pure prompt-side logic: gating (D13), in-context detection (D3), idempotent injection (H2).

import { normalizeText } from './canonical';
import { selectedContent } from './manifest';
import { isTextPart, MEMORY_MARKER, type MarkerAt } from './placement';
import type { HostMessage, PromptMessage } from './types';

export const PACKET_TAG = '<NarrativeMemory version="0" source="nmos">';
export const GUARD_LINE = "(The user's most recent message comes before this memory and has already happened; where the two differ, that message wins.)";
export const GUARD_RESERVE_TOKENS = 40;

/** A prompt message's text: a string as it is, a multipart message's text parts joined (images and other parts carry
 *  no text); anything else has none. */
export function contentText(content: unknown): string {
  if (typeof content === 'string') return content;
  if (Array.isArray(content)) return content.filter(isTextPart).map((part) => part.text).join('\n');
  return '';
}

const norm = (value: unknown): string => normalizeText(value).trim();

/** Whether the host sends this message by itself (HOST-FACTS S8/S8b): a disabled message, a comment and a "Cut
 *  Messages for AI" message (`disabled: 'allBefore'`) are never sent. Use `activeStartIndex` for the messages a cut
 *  hides before it. */
export function isActive(message: HostMessage | null | undefined): boolean {
  return message != null && message.disabled !== true && message.disabled !== 'allBefore' && !message.isComment;
}

/** The first message the host can send: the one after the newest `disabled: 'allBefore'` message, which hides itself
 *  and every message before it (HOST-FACTS S8b; the sidecar's active view reads it the same way), else 0. */
export function activeStartIndex(messages: HostMessage[]): number {
  if (!Array.isArray(messages)) return 0;
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    if (messages[i]?.disabled === 'allBefore') return i + 1;
  }
  return 0;
}

export function latestUserIndex(messages: HostMessage[]): number {
  if (!Array.isArray(messages)) return -1;
  const start = activeStartIndex(messages);
  for (let i = messages.length - 1; i >= start; i -= 1) {
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
  if (anchor.length >= SHORT_TURN) {
    // Cleaned-text containment instead of equality: input scripts may wrap or reshape the user turn.
    for (let i = prompt.length - 1; i >= 0; i -= 1) {
      if (prompt[i]?.role === 'assistant') continue;
      const sent = cleanText(contentText(prompt[i]?.content));
      if (sent.includes(anchor)) return i;
    }
    return -1;
  }
  // A short turn (`응`, `네`, `1`, `go`) is inside many other words (`반응`) and instruction blocks: a message that is
  // exactly the turn first, then a user message holding it as a word of its own, then any other non-assistant one.
  const texts = prompt.map((m) => cleanText(contentText(m?.content)));
  // The turn comes after the chat before it: an older message with the same short text (`응` twice) must not win over
  // a wrapped current one, so the search starts after the newest prompt message matched to earlier chat, and only
  // with nothing there over the whole prompt.
  const latest = latestUserIndex(hostMessages);
  const matches = matchPromptToHost(prompt, hostMessages);
  let floor = -1;
  for (const [hostIdx, promptIdx] of matches) if (hostIdx < latest && promptIdx > floor) floor = promptIdx;
  const search = (from: number): number => {
    const newest = (ok: (i: number) => boolean): number => {
      for (let i = prompt.length - 1; i > from; i -= 1) if (prompt[i]?.role !== 'assistant' && ok(i)) return i;
      return -1;
    };
    let at = newest((i) => texts[i] === anchor);
    if (at < 0) at = newest((i) => prompt[i]?.role === 'user' && holdsWord(texts[i] as string, anchor));
    if (at < 0) at = newest((i) => holdsWord(texts[i] as string, anchor));
    return at;
  };
  let found = search(floor);
  if (found < 0 && floor >= 0) found = search(-1);
  // An auxiliary call (a script's own model call) can hold a short word with none of the chat around it: a chat with
  // earlier messages long enough to match has at least one of them in the main generation's prompt.
  if (found < 0 || (matches.size === 0 && hasAnchorableHistory(hostMessages, latest))) return -1;
  return found;
}

/** A user turn shorter than this is matched with the care of `userTurnIndex`. */
const SHORT_TURN = 6;
const WORD_CHAR = /[\p{L}\p{N}]/u;

/** Whether `text` holds `word` not as part of a longer word (a letter or digit right before or after it). */
function holdsWord(text: string, word: string): boolean {
  const edgeStart = WORD_CHAR.test(word.charAt(0));
  const edgeEnd = WORD_CHAR.test(word.charAt(word.length - 1));
  for (let at = text.indexOf(word); at >= 0; at = text.indexOf(word, at + 1)) {
    const before = text.charAt(at - 1);
    const after = text.charAt(at + word.length);
    if ((!edgeStart || !before || !WORD_CHAR.test(before)) && (!edgeEnd || !after || !WORD_CHAR.test(after))) return true;
  }
  return false;
}

/** Whether the chat before the latest user message has a message long enough to be matched at all (without one,
 *  nothing can tell whether a prompt holds the chat). */
function hasAnchorableHistory(hostMessages: HostMessage[], latest: number): boolean {
  for (let i = activeStartIndex(hostMessages); i < latest; i += 1) {
    const m = hostMessages[i];
    if (isActive(m) && cleanText(selectedContent(m)).length >= MIN_ANCHOR) return true;
  }
  return false;
}

export function isMainGeneration(prompt: PromptMessage[], mode: unknown, hostMessages: HostMessage[]): boolean {
  return mode === 'model' && userTurnIndex(prompt, hostMessages) >= 0;
}

const PACKET_END = '</NarrativeMemory>';

/**
 * Whether the prompt already holds our packet (a retry, H2). A system message with the tag is one. With the chat's
 * messages, so is a user message (a preset's `[NMOS.memory]` in a user block) holding a whole packet, the tag to its
 * end, that is not text of the chat: a reply or user message quoting the tag, or pasting a packet, must not stop memory.
 */
export function hasPacket(prompt: PromptMessage[], hostMessages?: HostMessage[]): boolean {
  if (!Array.isArray(prompt)) return false;
  if (prompt.some((m) => m?.role === 'system' && contentText(m.content).includes(PACKET_TAG))) return true;
  if (!Array.isArray(hostMessages)) return false;
  let chat: { raw: string; clean: string }[] | null = null;
  const echoed = (block: string): boolean => {
    chat ??= hostMessages.map((h) => {
      const raw = selectedContent(h);
      return { raw, clean: cleanText(raw) };
    });
    // Verbatim, or as visible text when that is long enough to tell (a short one is in many chat messages).
    const clean = cleanText(block);
    return chat.some((h) => h.raw.includes(block) || (clean.length >= 2 * MIN_ANCHOR && h.clean.includes(clean)));
  };
  return prompt.some((m) => {
    if (m?.role !== 'user') return false;
    const text = contentText(m.content);
    for (let at = text.indexOf(PACKET_TAG); at >= 0; at = text.indexOf(PACKET_TAG, at + 1)) {
      const end = text.indexOf(PACKET_END, at);
      if (end < 0) return false;
      if (!echoed(text.slice(at, end + PACKET_END.length))) return true;
    }
    return false;
  });
}

/** Visible text only: host regex scripts and status HTML often reshape what is sent to the model. Model reasoning
 *  (`<Thoughts>`, `<think>`, `<thinking>`) is not story either: the host keeps it in the message and sends it apart
 *  (`thoughts`), so it is dropped like the sidecar's `packet.py` drops it (paired tags only). */
export function cleanText(value: unknown): string {
  return normalizeText(value)
    .replace(/<(style|script|thoughts|think|thinking)\b[^>]*>[\s\S]*?<\/\1\s*>/gi, ' ')
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
  minAnchor = MIN_ANCHOR,
  maxMisses = 3,
): Map<number, number> {
  const matches = new Map<number, number>();
  if (!Array.isArray(prompt) || !Array.isArray(hostMessages)) return matches;
  const texts = prompt.map((m) => cleanText(contentText(m?.content)));
  const start = activeStartIndex(hostMessages);
  let pointer = texts.length - 1;
  let misses = 0;
  for (let i = hostMessages.length - 1; i >= start && pointer >= 0; i -= 1) {
    const m = hostMessages[i];
    if (!m || !isActive(m)) continue;
    const text = cleanText(selectedContent(m));
    if (text.length < minAnchor) continue;
    const anchor = anchorOf(text);
    // The newest prompt message of a fitting role wins; one of the other role (a user message sent as the model's,
    // or a reply inside a user block: a preset that wraps the chat) only when no fitting one holds the text.
    let found = -1;
    let other = -1;
    for (let k = pointer; k >= 0; k -= 1) {
      if (!(texts[k] as string).includes(anchor)) continue;
      if (rolesFit(m.role, prompt[k]?.role)) {
        found = k;
        break;
      }
      if (other < 0) other = k;
    }
    if (found < 0) found = other;
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

/** `matchPromptToHost`'s default: shorter host messages are never anchor-matched. */
export const MIN_ANCHOR = 16;

/** A user message is not the model's (assistant) and a reply is not the user's; a system message may hold either. */
function rolesFit(host: HostMessage['role'], prompt: unknown): boolean {
  return host === 'user' ? prompt !== 'assistant' : prompt !== 'user';
}

/** How many `[NMOS.memory]` literals `text` holds. */
export function markerCount(text: string): number {
  return text ? text.split(MEMORY_MARKER).length - 1 : 0;
}

/**
 * Prompt indices of chat messages whose `[NMOS.memory]` is the chat's own text (a message that mentions the
 * placeholder), not a preset's placeholder: each anchor-matched message holding no more markers than its host
 * message does. Placement (and trimming) ignores the markers there.
 */
export function historyMarkerIndices(prompt: PromptMessage[], hostMessages: HostMessage[],
                                     matches = matchPromptToHost(prompt, hostMessages)): Set<number> {
  const out = new Set<number>();
  for (const [hostIdx, promptIdx] of matches) {
    const own = markerCount(selectedContent(hostMessages[hostIdx]));
    if (own > 0 && markerCount(contentText(prompt[promptIdx]?.content)) <= own) out.add(promptIdx);
  }
  return out;
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
  const start = activeStartIndex(hostMessages);
  for (let i = userIndex - 1; i >= start; i -= 1) {
    const m = hostMessages[i] as HostMessage;
    if (m.role === 'char' && isActive(m)) {
      previousAi = normalizeText(selectedContent(m));
      break;
    }
  }
  return { query, previousAi };
}
