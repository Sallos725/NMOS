// Canon sources (Phase 14, ADR 0045): what the card, the chat's author's note, its persona and the lorebooks say,
// as the host shows them to this chat. Pure: the host reads are in host.ts, the sync in core.ts.

import { canonicalJson, normalizeText } from './canonical';
import { sha256Hex } from './hash';
import type { HostChat, PromptMessage } from './types';

/** A lorebook entry as `getCurrentLorebookEntries()` returns it (H19). */
export interface HostLoreEntry {
  id?: string;
  key?: string;
  secondkey?: string;
  comment?: string;
  content?: string;
  mode?: string;
  alwaysActive?: boolean;
  folder?: string;
}

/** The card's story fields, read with the character off the request path (H19). */
export interface HostCard {
  name?: string;
  desc?: string;
  personality?: string;
  scenario?: string;
  firstMessage?: string;
  alternateGreetings?: string[];
  globalLore?: HostLoreEntry[];
}

export interface HostPersona {
  id?: string;
  name?: string;
  personaPrompt?: string;
}

export interface CanonText {
  key: string;
  text: string;
  metadata: Record<string, unknown>;
}

const ID = /^[A-Za-z0-9_.:-]{1,110}$/; // the sidecar's key pattern; `~` is kept for the suffix of a repeated key
/** A text longer than this is not kept (the sidecar takes up to 2,000,000 characters per text). */
export const MAX_CANON_CHARS = 1_900_000;

/** FNV-1a (32-bit), for a stable key of an entry that has no id. */
function fnv(text: string): string {
  let h = 0x811c9dc5;
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h.toString(16).padStart(8, '0');
}

/** An entry's canon key: its host id, else a hash of what names it (not its content, so an edit keeps the key). */
export function loreKey(entry: HostLoreEntry): string {
  if (typeof entry.id === 'string' && ID.test(entry.id)) return `lore:${entry.id}`;
  return `lore:f${fnv([entry.comment ?? '', entry.key ?? '', entry.secondkey ?? '', entry.mode ?? ''].join('\u0000'))}`;
}

function keysOf(entry: HostLoreEntry): string[] {
  return `${entry.key ?? ''},${entry.secondkey ?? ''}`.split(/[,\n]/).map((k) => k.trim()).filter(Boolean);
}

const text = (value: unknown): string => (typeof value === 'string' ? value.trim() : '');

function same(a: HostLoreEntry, b: HostLoreEntry): boolean {
  return a === b || (!!a.id && a.id === b.id) || (a.content === b.content && a.key === b.key && a.comment === b.comment);
}

/**
 * The chat's canon: the card's story fields and the greeting it started from, the author's note, the persona's
 * prompt, and every lorebook entry with content (folders are structure, not canon). Instructions, example messages
 * and assets are not canon (PHASE-14 Q1).
 */
export function canonTexts(card: HostCard | null, chat: HostChat, lore: HostLoreEntry[], persona: HostPersona | null):
  CanonText[] {
  const out: CanonText[] = [];
  const add = (key: string, value: unknown, metadata: Record<string, unknown> = {}) => {
    const t = text(value);
    if (t && t.length <= MAX_CANON_CHARS) out.push({ key, text: t, metadata });
  };
  if (card) {
    for (const field of ['name', 'desc', 'personality', 'scenario'] as const) add(`card:${field}`, card[field], { field });
    const index = Number.isInteger(chat.fmIndex) ? Number(chat.fmIndex) : -1;
    add('card:greeting', index < 0 ? card.firstMessage : card.alternateGreetings?.[index], { field: 'greeting', index });
  }
  add('note', chat.note);
  if (persona) add('persona', persona.personaPrompt, { name: text(persona.name) || undefined, persona_id: persona.id });
  const local = Array.isArray(chat.localLore) ? chat.localLore : [];
  const global = Array.isArray(card?.globalLore) ? card!.globalLore! : [];
  const seen = new Map<string, number>();
  for (const entry of lore) {
    if (!entry || entry.mode === 'folder') continue;
    let key = loreKey(entry);
    const n = seen.get(key) ?? 0;
    seen.set(key, n + 1);
    if (n) key = `${key}~${n}`; // two entries alike in what names them: keep both, in host order
    const scope = local.some((e) => same(e, entry)) ? 'chat' : global.some((e) => same(e, entry)) ? 'character'
      : card ? 'module' : null;
    add(key, entry.content, { scope: scope ?? undefined, mode: entry.mode, always_active: !!entry.alwaysActive,
      keys: keysOf(entry), comment: text(entry.comment) || undefined });
  }
  return out;
}

/** The canon keys whose text the outgoing prompt holds (the host sent them; an entry it activated, H19). */
export function heldKeys(canon: CanonText[], prompt: PromptMessage[]): string[] {
  const all = normalizeText(prompt.map((m) => (typeof m?.content === 'string' ? m.content : '')).join('\n'));
  return canon.filter((c) => c.key !== 'card:name' && all.includes(normalizeText(c.text))).map((c) => c.key);
}

export interface CanonEntry {
  key: string;
  hash: string;
  metadata: Record<string, unknown>;
}

/** The hash a canon text is sent and kept under: SHA-256 of its normalized text (the sidecar's `content_hash`). */
export function canonHash(text: string): Promise<string> {
  return sha256Hex(normalizeText(text));
}

/** A manifest's id: SHA-256 of the canonical JSON of its entries in key order (the sidecar's `manifest_id`,
 *  fixtures/unit/canon-manifest-v1.json). */
export function canonManifestId(entries: CanonEntry[]): Promise<string> {
  const rows = entries.map((e) => ({ key: e.key, hash: e.hash, metadata: e.metadata ?? {} }))
    .sort((a, b) => (a.key < b.key ? -1 : a.key > b.key ? 1 : 0));
  return sha256Hex(canonicalJson(rows));
}
