import { canonicalJson, normalizeText } from './canonical';
import { sha256Hex } from './hash';
import type { Body, HostChat, HostMessage, ManifestMessage, ReconcileRequest } from './types';

export const HASH_FORMAT_VERSION = 1;
const SPECIAL_COMMENT = /\{\{specialcomment::[^]*?::\}\}/g;

export function selectedContent(message: HostMessage | undefined): string {
  const swipes = message?.swipes;
  const id = message?.swipeId;
  if (Array.isArray(swipes) && Number.isInteger(id) && (id as number) >= 0 && (id as number) < swipes.length) {
    return swipes[id as number] ?? '';
  }
  return message?.data ?? '';
}

export function revisionMetadata(message: HostMessage): Record<string, unknown> {
  const data = typeof message.data === 'string' ? message.data : '';
  return {
    chatId: message.chatId ?? null,
    role: message.role ?? null,
    saying: message.saying ?? null,
    name: message.name ?? null,
    otherUser: message.otherUser ?? null,
    isComment: message.isComment ?? null,
    disabled: message.disabled ?? null,
    swipeId: message.swipeId ?? null,
    generationId: message.generationInfo?.generationId ?? null,
    swipeCount: Array.isArray(message.swipes) ? message.swipes.length : 0,
    specialComments: data.match(SPECIAL_COMMENT) ?? [],
  };
}

export function hashPayload(message: HostMessage): Record<string, unknown> {
  const meta = revisionMetadata(message);
  return {
    v: HASH_FORMAT_VERSION,
    chatId: meta.chatId,
    role: meta.role,
    saying: meta.saying,
    name: meta.name,
    otherUser: meta.otherUser,
    isComment: meta.isComment,
    disabled: meta.disabled,
    swipeId: meta.swipeId,
    selectedContent: selectedContent(message),
    generationId: meta.generationId,
  };
}

/** Bodies by `bodyKey`, built only for the keys the sidecar asks for. */
export interface Bodies {
  get(key: string): Body | undefined;
}

export interface BuiltManifest {
  request: ReconcileRequest;
  bodies: Bodies;
  /** Messages hashed for this manifest (all of them without a cache). */
  hashed: number;
}

export const bodyKey = (logicalId: string, revisionHash: string): string => `${logicalId}\n${revisionHash}`;

export interface Labels {
  characterName?: string | null;
}

const LABEL_MAX = 200;

function labelOf(value: unknown): string | undefined {
  const text = typeof value === 'string' ? value.trim() : '';
  return text ? text.slice(0, LABEL_MAX) : undefined;
}

function manifestEntry(m: HostMessage, revisionHash: string): ManifestMessage {
  const meta = revisionMetadata(m);
  return {
    host_logical_id: String(m.chatId ?? ''),
    revision_hash: revisionHash,
    role: m.role,
    name: m.name ?? null,
    disabled: m.disabled ?? null,
    is_comment: m.isComment ?? null,
    swipe_id: m.swipeId ?? null,
    swipe_count: meta.swipeCount as number,
    generation_id: (meta.generationId as string | null) ?? null,
    special_comments: meta.specialComments as string[],
  };
}

/**
 * Every input of a message's hash and manifest entry, as primitives compared with `===`. Never a
 * digest: a collision would hide a change, the sidecar would see a noop, and stale memory would be
 * injected. `undefined` when a field is not a primitive (such a message is always hashed).
 */
type Snapshot = readonly unknown[];

function snapshotOf(m: HostMessage): Snapshot | undefined {
  const content = selectedContent(m);
  const data = typeof m.data === 'string' ? m.data : '';
  const out = [m.role, m.saying, m.name, m.otherUser, m.isComment, m.disabled, m.swipeId,
    m.generationInfo?.generationId, Array.isArray(m.swipes) ? m.swipes.length : 0, content,
    data === content ? null : data];
  return out.every((v) => v === null || v === undefined || typeof v !== 'object' && typeof v !== 'function')
    ? out : undefined;
}

function sameSnapshot(a: Snapshot, b: Snapshot): boolean {
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return false;
  return true;
}

interface Cached {
  snapshot: Snapshot;
  entry: ManifestMessage;
}

function finish(chat: HostChat, messages: HostMessage[], entries: ManifestMessage[], characterRef: string | null,
                labels: Labels, hashed: number): BuiltManifest {
  const index = new Map<string, number>();
  entries.forEach((e, i) => index.set(bodyKey(e.host_logical_id, e.revision_hash), i));
  const bodies: Bodies = {
    get(key) {
      const i = index.get(key);
      if (i === undefined) return undefined;
      const m = messages[i] as HostMessage;
      const e = entries[i] as ManifestMessage;
      return { host_logical_id: e.host_logical_id, revision_hash: e.revision_hash,
        content: normalizeText(selectedContent(m)), metadata: revisionMetadata(m) };
    },
  };
  return {
    request: {
      host: 'pocketrisu', chat_id: String(chat.id ?? ''), character_ref: characterRef,
      character_name: labelOf(labels.characterName), chat_name: labelOf(chat.name), hash_version: 1, messages: entries,
    },
    bodies,
    hashed,
  };
}

export async function buildManifest(chat: HostChat, characterRef: string | null, labels: Labels = {}): Promise<BuiltManifest> {
  const messages = Array.isArray(chat.message) ? chat.message : [];
  const hashes = await Promise.all(messages.map((m) => sha256Hex(canonicalJson(hashPayload(m)))));
  const entries = messages.map((m, i) => manifestEntry(m, hashes[i] as string));
  return finish(chat, messages, entries, characterRef, labels, messages.length);
}

const CACHED_CHATS = 2; // ≈24 MB of message text per 10,000-message chat

/**
 * `buildManifest` that hashes only new or changed messages (Track A, A2). Per host chat, it keeps each
 * message's hash inputs and entry, keyed by message id; order is rebuilt on every call, so order
 * changes stay visible. Output is identical to `buildManifest`.
 */
export function createManifestBuilder() {
  const chats = new Map<string, Map<string, Cached>>();

  return async function build(chat: HostChat, characterRef: string | null, labels: Labels = {}): Promise<BuiltManifest> {
    const messages = Array.isArray(chat.message) ? chat.message : [];
    const chatKey = String(chat.id ?? '');
    const previous = chats.get(chatKey) ?? new Map<string, Cached>();
    chats.delete(chatKey);
    const next = new Map<string, Cached>();
    const entries: (ManifestMessage | undefined)[] = new Array(messages.length);
    const snapshots: (Snapshot | undefined)[] = new Array(messages.length);
    const missing: number[] = [];
    const seen = new Set<string>();
    messages.forEach((m, i) => {
      const id = m.chatId;
      // Ids are unique within a chat (H6). A message without a usable id, or a repeat of an id, is
      // hashed every time and never cached.
      const snapshot = typeof id === 'string' && id !== '' && !seen.has(id) ? snapshotOf(m) : undefined;
      if (typeof id === 'string') seen.add(id);
      snapshots[i] = snapshot;
      const hit = snapshot ? previous.get(id as string) : undefined;
      if (hit && sameSnapshot(hit.snapshot, snapshot!)) {
        entries[i] = hit.entry;
        next.set(id as string, hit);
      } else {
        missing.push(i);
      }
    });
    const hashes = await Promise.all(missing.map((i) => sha256Hex(canonicalJson(hashPayload(messages[i] as HostMessage)))));
    missing.forEach((i, j) => {
      const m = messages[i] as HostMessage;
      const entry = manifestEntry(m, hashes[j] as string);
      entries[i] = entry;
      const snapshot = snapshots[i];
      if (snapshot) next.set(m.chatId as string, { snapshot, entry });
    });
    chats.set(chatKey, next);
    while (chats.size > CACHED_CHATS) chats.delete(chats.keys().next().value as string);
    return finish(chat, messages, entries as ManifestMessage[], characterRef, labels, missing.length);
  };
}
