/** Pure helpers for cleaning up conversations missing from the host's active chat list (PHASE-68, H22). */

export type HostChatScan =
  | { ok: true; chatIds: string[]; characterCount: number }
  | { ok: false; reason: 'unsupported' | 'denied' | 'invalid' };

export interface OrphanCarryTarget {
  id: string;
  character: string | null;
  chat: string | null;
  mode: string;
  target_missing: boolean;
}

export interface OrphanRow {
  id: string;
  host_chat_ref: string;
  character: string | null;
  chat: string | null;
  messages: number;
  commits: number;
  created_at: string | null;
  last_retrieval: string | null;
  carried_by: OrphanCarryTarget[];
  branch_children: number;
}

export interface OrphanPreview {
  host: string;
  total_host_conversations: number;
  matched_active: number;
  orphans: OrphanRow[];
}

export interface BatchDeleteResult {
  deleted: { id: string; counts: Record<string, number> }[];
  not_found: string[];
  totals: {
    conversations: number;
    messages: number;
    revisions: number;
    carry_links: number;
    [key: string]: number;
  };
}

export interface OrphanSelectionSummary {
  selectedCount: number;
  totalCount: number;
  allSelected: boolean;
  indeterminate: boolean;
  totalMessages: number;
  activeCarryTargets: OrphanCarryTarget[];
}

export const DELETE_BATCH_CHUNK = 500;

/**
 * Parse `risuai.getDatabase(['characters'])` strictly (H22):
 * - `null` / `undefined` means permission denied (`denied`), NEVER an empty chat list.
 * - Non-object or non-array `characters` (or a character whose `chats` field is non-nullish and not an array)
 *   fails closed as `invalid` so a host schema change can never wipe live chats.
 */
export function parseHostCharacters(db: unknown): HostChatScan {
  if (db === null || db === undefined) return { ok: false, reason: 'denied' };
  if (typeof db !== 'object' || !Array.isArray((db as { characters?: unknown }).characters)) {
    return { ok: false, reason: 'invalid' };
  }
  const chars = (db as { characters: unknown[] }).characters;
  const seen = new Set<string>();
  let characterCount = 0;
  for (const ch of chars) {
    if (ch === null || ch === undefined) continue;
    if (typeof ch !== 'object') return { ok: false, reason: 'invalid' };
    characterCount += 1;
    const chats = (ch as { chats?: unknown }).chats;
    if (chats === undefined || chats === null) continue;
    if (!Array.isArray(chats)) return { ok: false, reason: 'invalid' };
    for (const chat of chats) {
      if (chat === null || chat === undefined) continue;
      if (typeof chat !== 'object') continue;
      const id = (chat as { id?: unknown }).id;
      if (typeof id === 'string' && id.trim().length > 0) {
        // Keep host chat IDs verbatim (matching `host.ts` / `conversation.host_chat_ref`).
        seen.add(id);
      }
    }
  }
  return { ok: true, chatIds: Array.from(seen), characterCount };
}

/** Human-readable display label for an orphan row or carry target. */
export function orphanLabel(
  row: { character?: string | null; chat?: string | null; host_chat_ref?: string | null; id?: string | null },
  fallback: string,
): string {
  const ch = (row.character ?? '').trim();
  const ti = (row.chat ?? '').trim();
  if (ch && ti && ti !== ch) return `${ch} · ${ti}`;
  if (ch) return ch;
  if (ti) return ti;
  const ref = (row.host_chat_ref ?? '').trim();
  if (ref) return ref.slice(0, 8);
  const id = (row.id ?? '').trim();
  return id ? id.slice(0, 8) : fallback;
}

/** Compute live selection counts, select-all checkbox state, and unique active carry targets affected. */
export function selectionSummary(orphans: readonly OrphanRow[], selectedIds: ReadonlySet<string>): OrphanSelectionSummary {
  const totalCount = orphans.length;
  let selectedCount = 0;
  let totalMessages = 0;
  const activeMap = new Map<string, OrphanCarryTarget>();
  for (const row of orphans) {
    if (!selectedIds.has(row.id)) continue;
    selectedCount += 1;
    totalMessages += Number.isFinite(row.messages) && row.messages > 0 ? row.messages : 0;
    for (const target of row.carried_by ?? []) {
      if (!target.target_missing && !activeMap.has(target.id)) {
        activeMap.set(target.id, target);
      }
    }
  }
  return {
    selectedCount,
    totalCount,
    allSelected: totalCount > 0 && selectedCount === totalCount,
    indeterminate: selectedCount > 0 && selectedCount < totalCount,
    totalMessages,
    activeCarryTargets: Array.from(activeMap.values()),
  };
}

/** Split selected IDs into chunks within the sidecar's per-request cap (`MAX_BATCH_DELETE_IDS`). */
export function chunkIds(ids: readonly string[], size = DELETE_BATCH_CHUNK): string[][] {
  const out: string[][] = [];
  const step = Math.max(1, Math.floor(size));
  for (let i = 0; i < ids.length; i += step) out.push(ids.slice(i, i + step));
  return out;
}

/** Format an ISO timestamp in local `YYYY-MM-DD HH:MM` form; falls back to the raw prefix on invalid dates. */
export function formatOrphanDate(iso: string | null | undefined): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso.slice(0, 16).replace('T', ' ');
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
