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

export interface BuiltManifest {
  request: ReconcileRequest;
  bodies: Map<string, Body>; // key: `${host_logical_id}\n${revision_hash}`
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

export async function buildManifest(chat: HostChat, characterRef: string | null, labels: Labels = {}): Promise<BuiltManifest> {
  const messages = Array.isArray(chat.message) ? chat.message : [];
  const hashes = await Promise.all(messages.map((m) => sha256Hex(canonicalJson(hashPayload(m)))));
  const bodies = new Map<string, Body>();
  const entries: ManifestMessage[] = messages.map((m, i) => {
    const meta = revisionMetadata(m);
    const revisionHash = hashes[i] as string;
    const logicalId = String(m.chatId ?? '');
    bodies.set(bodyKey(logicalId, revisionHash), {
      host_logical_id: logicalId,
      revision_hash: revisionHash,
      content: normalizeText(selectedContent(m)),
      metadata: meta,
    });
    return {
      host_logical_id: logicalId,
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
  });
  return {
    request: {
      host: 'pocketrisu', chat_id: String(chat.id ?? ''), character_ref: characterRef,
      character_name: labelOf(labels.characterName), chat_name: labelOf(chat.name), hash_version: 1, messages: entries,
    },
    bodies,
  };
}
