// Pure `[NMOS.memory]` placeholder detection and replacement (Phase 60 S2.3, ADR 0083).

import type { PromptMessage } from './types';

export const MEMORY_MARKER = '[NMOS.memory]';

export interface MarkerAt {
  message: number;
  part: number | null;
  offset: number;
}

export interface TextPart {
  type: 'text';
  text: string;
  [key: string]: unknown;
}

export function isTextPart(part: unknown): part is TextPart {
  return typeof part === 'object' && part !== null && !Array.isArray(part)
    && (part as Record<string, unknown>).type === 'text'
    && typeof (part as Record<string, unknown>).text === 'string';
}

/** First occurrence of `[NMOS.memory]`, scanning messages and multipart parts in order. */
export function findMarker(prompt: unknown): MarkerAt | null {
  if (!Array.isArray(prompt)) return null;
  for (let i = 0; i < prompt.length; i += 1) {
    const m = prompt[i];
    if (!m || typeof m !== 'object') continue;
    const content = (m as Record<string, unknown>).content;
    if (typeof content === 'string') {
      const offset = content.indexOf(MEMORY_MARKER);
      if (offset >= 0) return { message: i, part: null, offset };
    } else if (Array.isArray(content)) {
      for (let j = 0; j < content.length; j += 1) {
        const part = content[j];
        if (!isTextPart(part)) continue;
        const offset = part.text.indexOf(MEMORY_MARKER);
        if (offset >= 0) return { message: i, part: j, offset };
      }
    }
  }
  return null;
}

function replaceInString(text: string, packet: string, placed: boolean): { text: string; changed: boolean; placed: boolean } {
  if (!text.includes(MEMORY_MARKER)) return { text, changed: false, placed };
  const parts = text.split(MEMORY_MARKER);
  if (placed) return { text: parts.join(''), changed: true, placed: true };
  return { text: `${parts[0] ?? ''}${packet}${parts.slice(1).join('')}`, changed: true, placed: true };
}

/**
 * Replaces the first `[NMOS.memory]` with `packet` (cleaned of any literal markers) and removes every
 * subsequent occurrence. Never mutates inputs; returns the original array reference when no marker is found.
 */
export function resolvePlaceholders(prompt: PromptMessage[], packet: string): PromptMessage[] {
  if (!Array.isArray(prompt)) return prompt;
  const cleanPacket = typeof packet === 'string' ? packet.split(MEMORY_MARKER).join('') : '';
  let out: PromptMessage[] | null = null;
  let placed = false;

  for (let i = 0; i < prompt.length; i += 1) {
    const m = prompt[i];
    if (!m || typeof m !== 'object') continue;
    const content = m.content;
    if (typeof content === 'string') {
      const res = replaceInString(content, cleanPacket, placed);
      placed = res.placed;
      if (res.changed) {
        if (out === null) out = prompt.slice();
        out[i] = { ...m, content: res.text };
      }
    } else if (Array.isArray(content)) {
      let newParts: unknown[] | null = null;
      for (let j = 0; j < content.length; j += 1) {
        const part = content[j];
        if (!isTextPart(part)) continue;
        const res = replaceInString(part.text, cleanPacket, placed);
        placed = res.placed;
        if (res.changed) {
          if (newParts === null) newParts = content.slice();
          newParts[j] = { ...part, text: res.text };
        }
      }
      if (newParts !== null) {
        if (out === null) out = prompt.slice();
        out[i] = { ...m, content: newParts };
      }
    }
  }

  return out ?? prompt;
}

/** Removes every `[NMOS.memory]` occurrence without placing a packet. */
export function stripMarkers(prompt: PromptMessage[]): PromptMessage[] {
  return resolvePlaceholders(prompt, '');
}

/**
 * True when the raw string content of some message or the raw `text` of some multipart text part
 * contains `text` (non-empty). Checks raw text rather than JSON-stringified content.
 */
export function holdsText(prompt: unknown, text: string): boolean {
  if (!text || typeof text !== 'string' || !Array.isArray(prompt)) return false;
  for (let i = 0; i < prompt.length; i += 1) {
    const m = prompt[i];
    if (!m || typeof m !== 'object') continue;
    const content = (m as Record<string, unknown>).content;
    if (typeof content === 'string') {
      if (content.includes(text)) return true;
    } else if (Array.isArray(content)) {
      for (let j = 0; j < content.length; j += 1) {
        const part = content[j];
        if (isTextPart(part) && part.text.includes(text)) return true;
      }
    }
  }
  return false;
}
