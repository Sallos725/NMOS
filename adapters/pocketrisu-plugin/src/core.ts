// Request-path orchestration. Host access comes in through `HostPort`; everything fails open.

import type { Method } from './restore';
import type { MemoryFit } from './budget';
import { PLUGIN_BUILD } from './build';
import { canonHash, canonManifestId, canonTexts, heldKeys, type CanonEntry, type CanonText, type HostCard, type HostLoreEntry,
  type HostPersona } from './canon';
import { canonicalJson } from './canonical';
import { sha256Hex } from './hash';
import { deadlineAdvice, formatMs } from './deadline';
import { DEFAULT_DEADLINE_MS, DEFAULT_KEEP_RECENT_TURNS, MAX_KEEP_RECENT_TURNS, MIN_KEEP_RECENT_TURNS } from './form';
import { t, type Lang, type StringKey } from './i18n';
import { bodyKey, createManifestBuilder, hashPayload, type Bodies } from './manifest';
import type { ActivityEvent } from './hud';
import { findMarker, holdsText, MEMORY_MARKER, resolvePlaceholders, stripMarkers } from './placement';
import { GUARD_RESERVE_TOKENS, hasPacket, historyMarkerIndices, inContextIds, injectPacket, landsAfterUserTurn,
  matchPromptToHost, queryTexts, userTurnIndex, withGuard, type InjectPosition } from './prompt';
import { canTrimPrompt, createTrimScan, trimPrompt } from './trim';
import type { HostChat, HostMessage, HostPersonas, PromptMessage, ReconcileRequest } from './types';
import { failureKind, INSECURE_ERROR, secureContext } from './failure';

export interface Settings {
  sidecarUrl: string;
  authToken: string;
  enabled: boolean;
  reservedMemoryTokens: number;
  deadlineMs: number;
  injectPosition: InjectPosition;
  /** 'direct' = browser fetch (proxy fallback); 'server' = always via the PocketRisu server. */
  route: 'direct' | 'server';
  language: Lang;
  /** Host chat ids NMOS is switched off for (ADR 0048); none when missing. */
  offChats?: string[];
  /** Leave old dialogue out in steps once memory covers it (PHASE-60 S1); off when missing. */
  trimOldTurns?: boolean;
  /** Recent turns always sent when trimming, and the step the cut moves by; 16 when missing. */
  keepRecentTurns?: number;
}

export interface HttpResult {
  status: number;
  json: unknown;
}

/** A file's bytes as the sidecar sent them (an archive, ADR 0050); `json` only for an error answer. */
export interface FileResult {
  status: number;
  bytes: ArrayBuffer | null;
  json: unknown;
}

export interface HostPort {
  settings(): Promise<Settings>;
  currentChat(): Promise<HostChat | null>;
  /** Name of the bot that owns chat `chatId` (a display label only). May be slow: never awaited on the request path. */
  characterName?(chatId: string): Promise<string | null>;
  /** The card of the bot that owns chat `chatId`, with its name (ADR 0045). Clones the chat (H19): never awaited on
   *  the request path. When present it replaces `characterName`. */
  card?(chatId: string): Promise<HostCard | null>;
  /** Every lorebook entry the host shows the current chat (about 1 ms, H19). */
  lorebook?(): Promise<HostLoreEntry[]>;
  /**
   * The host's personas (ADR 0023), or null when the host refuses. The first call may show the host's
   * permission dialog, so it is made at load (`warmPersonas`) and never awaited on the request path.
   */
  personas?(): Promise<HostPersonas | null>;
  request(method: Method, url: string, body: unknown, headers: Record<string, string>,
          timeoutMs: number, route: Settings['route']): Promise<HttpResult>;
  /** A GET whose answer is a file, as bytes (the panel's Export, H21). */
  requestFile?(url: string, headers: Record<string, string>, timeoutMs: number,
               route: Settings['route']): Promise<FileResult>;
  warn(...args: unknown[]): void;
  debug(...args: unknown[]): void;
  now(): number;
  /** The host's alert dialog (one global dialog: shown only after a reply, never during a request). */
  alert?(message: string): void;
}

class DeadlineError extends Error {}

interface ReconcileResult {
  conversation_id?: string;
  status: 'noop' | 'applied' | 'needs_bodies';
  active_commit: string | null;
  manifest_hash: string;
  needed_bodies?: { host_logical_id: string; revision_hash: string }[];
}

interface CacheEntry {
  packet: string;
  expires: number;
  failed?: boolean;
  memory?: MemoryFit | null;
  vectors?: Vectors | null;
  /** The canon the packet was built with (its manifest id and what the prompt held): another one misses. */
  canon?: string;
  /** The sidecar's old-dialogue boundary for this state (PHASE-60 S1); only when trimming was asked for. */
  trim?: TrimDecision | null;
  coverage?: RecallCoverage | null;
  /** The host chat it was built for (an empty packet of it is dropped after a reply, `onOutput`). */
  chatId?: string;
}

/** The sidecar's answer on old dialogue (PHASE-60 S1): the host id of the first message to keep, or why none. */
export interface TrimDecision {
  keepFromId: string | null;
  keepFromTurn: number | null;
  reason: string | null;
}

/** How far memory has got for the head (PHASE-60 S1): the latest turn an extraction serves, and the latest turn the
 *  trimming boundary may move to. Older sidecars send none. */
export interface RecallCoverage {
  recordedThroughTurn: number | null;
  coveredThroughTurn: number | null;
}

/** What trimming did to this request (PHASE-60 S1), for the status tab. */
export interface TrimOutcome {
  dropped: number;
  savedTokens: number;
  reason: string | null;
  /** The sidecar's boundary turn, only when messages were left out. */
  keepFromTurn: number | null;
}

const FAILED_TRIM: TrimDecision = { keepFromId: null, keepFromTurn: null, reason: 'failed' };
/** Trimming is on but this prompt cannot take a cut: no `trim` was asked for, or the boundary was refused. */
const FORMAT_TRIM: TrimDecision = { keepFromId: null, keepFromTurn: null, reason: 'format' };

/** Recent turns always sent when trimming is on, kept within 4..200; 0 when it is off (no `trim` in the request). */
export function keepRecentTurnsOf(settings: Settings): number {
  if (!settings.trimOldTurns) return 0;
  const n = settings.keepRecentTurns;
  const k = typeof n === 'number' && Number.isFinite(n) && n > 0 ? Math.floor(n) : DEFAULT_KEEP_RECENT_TURNS;
  return Math.min(MAX_KEEP_RECENT_TURNS, Math.max(MIN_KEEP_RECENT_TURNS, k));
}

const finiteOrNull = (value: unknown): number | null =>
  typeof value === 'number' && Number.isFinite(value) ? value : null;

/** The `trim` answer of a `/v1/retrieve` that asked for it: an older sidecar sends none (`unsupported`), and a
 *  stale answer never cuts (`failed`). Anything else malformed is `failed`, never a boundary. */
export function trimDecisionOf(fresh: boolean, trim: unknown): TrimDecision {
  if (!fresh) return FAILED_TRIM;
  if (!trim || typeof trim !== 'object') return { keepFromId: null, keepFromTurn: null, reason: 'unsupported' };
  const t = trim as { keep_from_id?: unknown; keep_from_turn?: unknown; reason?: unknown };
  const keepFromId = typeof t.keep_from_id === 'string' && t.keep_from_id ? t.keep_from_id : null;
  const reason = typeof t.reason === 'string' ? t.reason : null;
  if (!keepFromId && reason === null) return FAILED_TRIM;
  return { keepFromId, keepFromTurn: finiteOrNull(t.keep_from_turn), reason };
}

/** The `coverage` answer of a `/v1/retrieve`, or null when it has none (an older sidecar). */
export function coverageOf(coverage: unknown): RecallCoverage | null {
  if (!coverage || typeof coverage !== 'object') return null;
  const c = coverage as { recorded_through_turn?: unknown; covered_through_turn?: unknown };
  return { recordedThroughTurn: finiteOrNull(c.recorded_through_turn), coveredThroughTurn: finiteOrNull(c.covered_through_turn) };
}

/** Whether the sidecar's recall searched vectors (PHASE-15 Q5, K34): "fallback" is lexical only because the embedder
 *  failed or did not answer in time. Older sidecars send none. */
export type Vectors = 'on' | 'off' | 'fallback';

const SUCCESS_TTL_MS = 10 * 60_000;
/** An empty packet (nothing relevant yet) is reused for this long only: memory of a young chat fills in as its
 *  replies are extracted. */
const EMPTY_TTL_MS = 60_000;
const FAILURE_TTL_MS = 30_000;
/** After the prompt refused a boundary, trimming is not asked for while it still refuses there, up to this long. */
const REFUSED_TRIM_TTL_MS = 10 * 60_000;
const CACHE_LIMIT = 64;
const RETRY_MEMO_TTL_MS = 120_000;
const RETRY_MEMO_LIMIT = 4;
const BODY_CHUNK = 250;

export interface LastRequest {
  at: number;
  ms: number;
  packetChars: number;
  /** The memory text this request carried, for the status tab; kept in memory only. */
  packet: string;
  outcome: 'injected' | 'nothing-relevant' | 'failed' | 'skipped';
  error?: string;
  /** The deadline this request had. */
  deadlineMs: number;
  /** Cut at the deadline, but recall answered later: how long the whole request took (audit A-09). */
  neededMs?: number;
  /** The memory budget this request had, and what it left out (ADR 0036). */
  budgetTokens?: number;
  memory?: MemoryFit | null;
  vectors?: Vectors | null;
  /** Old-dialogue trimming (PHASE-60 S1); only when it is on. */
  trim?: TrimOutcome;
  coverage?: RecallCoverage | null;
}

export interface StatusInfo {
  enabled: boolean;
  sidecarUrl: string;
  language: Lang;
  connected: boolean;
  version?: string;
  features?: Record<string, boolean>;
  error?: string;
  last: LastRequest | null;
  /** The plugin build the sidecar ships (ADR 0037); null when it does not know one. */
  pluginExpected?: string | null;
  /** The page has no Web Crypto (plain HTTP on a LAN address): no request can be prepared (audit F24). */
  insecure?: boolean;
  /** How the sidecar was installed (`bundle`), when it says. */
  install?: string | null;
}

const NAME_TTL_MS = 10 * 60_000;
const NAMES_LIMIT = 8; // bounded card + globalLore retention for iPhone Safari/WebKit memory
const CANON_TIMEOUT_MS = 30_000;
const CANON_ROUNDS = 20;
const CANON_BATCH_CHARS = 800_000; // texts per canon call (a lorebook can hold 400k+ characters)
const TEXT_HASH_LIMIT = 512;
const TEXT_HASH_CHARS_LIMIT = 2_000_000; // ≈4 MB UTF-16 max retained canon text keys
const TEXT_HASH_SINGLE_MAX = 200_000; // skip retaining huge single texts in the hash cache

interface CanonSnapshot {
  id: string;
  entries: CanonEntry[];
  texts: CanonText[];
  observedAt: number;
}

interface CanonObservation {
  held: string[];
  snapshot: CanonSnapshot | null;
}
const PERSONA_TTL_MS = 5_000; // a persona switch reaches the sidecar within this (it is re-read in the background)

/** The persona the host uses for `{{user}}` in this chat: the chat-bound one, else the selected one. */
export function personaOf(chat: HostChat, host: HostPersonas): string | null {
  const list = Array.isArray(host.personas) ? host.personas : [];
  const bound = chat.bindedPersona ? list.find((p) => p?.id === chat.bindedPersona) : undefined;
  const name = (bound ?? list[host.selected])?.name;
  return typeof name === 'string' && name.trim() ? name.trim() : null;
}

/** How long after a reply its chat is synced in the background (G6), unless a request or another reply comes first;
 *  only while the sidecar reports `extraction.on_output: true` (it then extracts the reply early, PHASE-67). */
export const OUTPUT_SYNC_MS = 20_000;
/** The background sync's own time limit: it holds no request, so it is not cut at the request deadline. */
const OUTPUT_SYNC_TIMEOUT_MS = 30_000;
/** A request of the chat a background sync is still running for waits this long at most for it to end. */
const OUTPUT_SYNC_WAIT_MS = 1000;

/** How often the sidecar's settings are read again in the background for `extraction.on_output` (G6): a change made
 *  anywhere but this panel is seen within this plus `CONFIG_TIMEOUT_MS`; one saved from this panel at once. */
export const CONFIG_REFRESH_MS = 5 * 60_000;
const CONFIG_TIMEOUT_MS = 5000;

/** Timers for the background sync after a reply (G6), injectable so tests need not wait. */
export interface AdapterOptions {
  /** The wait after a reply; 0 or less: no background sync. `OUTPUT_SYNC_MS` when missing. */
  outputSyncMs?: number;
  setTimer?: (run: () => void, ms: number) => unknown;
  clearTimer?: (handle: unknown) => void;
  /** The timer of the slow background read of the sidecar's settings (`CONFIG_REFRESH_MS`), apart from `setTimer`. */
  setRefreshTimer?: (run: () => void, ms: number) => unknown;
}

/** `extraction.on_output` of a `GET`/`PUT /v1/config` answer: `false` when the sidecar does not report it (older than
 *  the switch), never anything but a boolean. */
export function outputSwitchOf(config: unknown): boolean {
  const on = (config as { extraction?: { on_output?: unknown } } | null)?.extraction?.on_output;
  return on === true;
}

/** `GET /v1/conversations/{id}/coverage` (with or without a query): the conversation id. */
const COVERAGE_PATH = /^\/v1\/conversations\/([^/?]+)\/coverage(?:\?.*)?$/;

/** What a coverage answer says the conversation's memory holds: the turns its extractor compiled, the messages
 *  embedded, the canon texts read, the facts and summaries made. `null` when it says none of these. */
export function memoryMark(answer: unknown): string | null {
  const a = (answer ?? {}) as Record<string, Record<string, unknown> | undefined>;
  const parts = [a.extraction?.compiled, a.embeddings?.embedded, a.canon?.read, a.produced?.facts, a.produced?.summaries]
    .map((v) => (typeof v === 'number' ? v : null));
  return parts.every((v) => v === null) ? null : JSON.stringify(parts);
}

/** The sidecar address as the switch is remembered for it. */
function sidecarKey(settings: Settings): string {
  return settings.sidecarUrl.replace(/\/+$/, '');
}

function defaultSetTimer(run: () => void, ms: number): unknown {
  const handle = setTimeout(run, ms);
  // In Node (the tests) a waiting sync must not keep the process alive; a browser timer has no `unref`.
  (handle as { unref?: () => void }).unref?.();
  return handle;
}

/** `onActivity` feeds the progress display (D28): called synchronously, never awaited, errors ignored. */
export function createAdapter(host: HostPort, onActivity?: (event: ActivityEvent) => void, options: AdapterOptions = {}) {
  const cache = new Map<string, CacheEntry>();
  const returnedMemo = new Map<string, number>(); // serialized returned prompt → expiry (H2 retry idempotence)
  const conversations = new Map<string, string>(); // host chat id → sidecar conversation id
  const names = new Map<string, { name: string | null; card: HostCard | null; at: number }>();
  const canonSent = new Map<string, string>(); // sidecar + conversation → the manifest id the sidecar has in force
  const canonQueue = new Map<string, { running: boolean; next: CanonSnapshot | null }>(); // one upload per chat at a time
  const textHashes = new Map<string, string>(); // canon text → its hash (texts rarely change: hashed once)
  let textHashChars = 0;
  const heldCard = new Map<string, string[]>(); // host chat id → the card fields its last prompt held
  const refusedTrim = new Map<string, { id: string; at: number }>(); // host chat id → a boundary its prompt refused
  let canonUnsupported = false; // an older sidecar has no /v1/sync/canon
  let personas: { value: HostPersonas | null; at: number } | null = null;
  const buildManifest = createManifestBuilder();
  let last: LastRequest | null = null;
  let epoch = 0; // bumped by every panel change: a request that saw another epoch neither caches nor injects
  // The background sync after a reply (G6): one waiting at a time, for the chat of the latest reply. `turnSeq` is bumped
  // by every main request and every reply: a sync that saw another one stops between its steps.
  const outputSyncMs = options.outputSyncMs ?? OUTPUT_SYNC_MS;
  const setTimer = options.setTimer ?? defaultSetTimer;
  const clearTimer = options.clearTimer ?? ((handle: unknown) => clearTimeout(handle as ReturnType<typeof setTimeout>));
  let outputTimer: unknown = null;
  let turnSeq = 0;
  let outputRunning: { chatId: string; done: Promise<void> } | null = null;
  // The sidecar's switch for extracting a reply right after it (`extraction.on_output`, PHASE-67), for the sidecar
  // address it was read from: the background sync runs only while it is `true` there. Learned from the answers of
  // `/v1/config` (the panel's, the read at load and the slow one after it), never on a request or a reply; `on: null`
  // is not known (not read yet, or the read failed): off.
  let outputSwitch: { url: string; on: boolean | null } | null = null;
  const setRefreshTimer = options.setRefreshTimer ?? defaultSetTimer;
  let refreshing = false;
  // Unloaded (or re-imported): no timer is set again, and the waiting ones are cleared (`dispose`).
  let disposed = false;
  let refreshHandle: unknown = null;
  // Config answers in order (review nit 9): each read or save is numbered when it starts. A read that started before
  // a save answered may carry the value from before it, and an answer older than one already noted is not news.
  let configStarted = 0;
  let configFence = 0;
  let configNoted = 0;
  let configSaved = 0;  // the newest save whose answer was noted: a save loses only to a newer save
  // A chat's cached packets are dropped when its memory may have moved (4.3.2): `dropSeq` counts the drops and
  // `droppedAt` holds a chat's last one, so a request that was already running then does not remember its packet.
  let dropSeq = 0;
  const droppedAt = new Map<string, number>();
  // What a conversation's coverage (`GET /v1/conversations/{id}/coverage`, the HUD's polls and the panel's reads) last
  // said its memory holds: a change means an extraction, embedding or canon read finished since.
  const coverageMarks = new Map<string, string>();
  // How many messages of a chat the plugin last synced (a request or the background sync): a background sync never
  // sends a snapshot shorter than that (a chat still loading reads as 0 messages, HOST-FACTS Q8 item 7, and an empty
  // manifest would retract the whole head).
  const syncedLength = new Map<string, number>();

  /** Drops every cached packet, and every packet still being fetched. */
  function invalidate(): void {
    epoch++;
    cache.clear();
  }

  function emit(event: ActivityEvent): void {
    try {
      onActivity?.(event);
    } catch {
      // the display must never affect a request
    }
  }

  function setName(chatId: string, entry: { name: string | null; card: HostCard | null; at: number }): void {
    if (disposed) return;
    names.delete(chatId);
    names.set(chatId, entry);
    while (names.size > NAMES_LIMIT) names.delete(names.keys().next().value as string);
  }

  /** Reads the chat's bot (its name and, with `card`, its card) in the background. */
  function refreshCharacter(chatId: string): void {
    const hit = names.get(chatId);
    setName(chatId, { name: hit?.name ?? null, card: hit?.card ?? null, at: host.now() });
    if (host.card) {
      host.card(chatId)
        .then((card) => {
          if (card) setName(chatId, { name: card.name?.trim() || null, card, at: host.now() });
        })
        .catch(() => {});
    } else if (host.characterName) {
      host.characterName(chatId)
        .then((name) => { if (name) setName(chatId, { name, card: null, at: host.now() }); })
        .catch(() => {});
    }
  }

  /** The bot name for this chat as last resolved; a stale or missing entry is refreshed in the background. */
  function characterName(chatId: string): string | null {
    const hit = names.get(chatId);
    if ((host.card || host.characterName) && (!hit || host.now() - hit.at > NAME_TTL_MS)) refreshCharacter(chatId);
    return hit?.name ?? null;
  }

  /** The persona the host uses for this chat, as last read (for its prompt, ADR 0045). */
  function personaRecord(chat: HostChat): HostPersona | null {
    const list = personas?.value?.personas ?? [];
    const bound = chat.bindedPersona ? list.find((p) => p?.id === chat.bindedPersona) : undefined;
    return bound ?? list[personas?.value?.selected ?? 0] ?? null;
  }

  /** The chat's canon as this request sees it: its texts, and once the card is known its manifest (ADR 0045). A failed
   *  lorebook read gives none, never an empty lorebook (which would end every entry). */
  async function observeCanon(chat: HostChat, prompt: PromptMessage[], deadline: number): Promise<CanonObservation | null> {
    if (!host.lorebook) return null;
    let lore: HostLoreEntry[];
    try {
      lore = await within(host.lorebook(), deadline, 'the lorebook');
    } catch (error) {
      if (error instanceof DeadlineError) throw error;
      return null;
    }
    if (!Array.isArray(lore)) return null;
    const character = names.get(chat.id!);
    const texts = canonTexts(character?.card ?? null, chat, lore, personaRecord(chat));
    const held = heldKeys(texts, prompt);
    // The card's description is in every prompt (H19): missing, the card was edited since it was read. Its
    // personality and scenario are only where the preset puts them: one the last prompt held and this one does not
    // was edited too (a preset that never sends them never refreshes the card for them).
    const fields = CARD_FIELDS.filter((f) => held.includes(f));
    const before = heldCard.get(chat.id!);
    heldCard.delete(chat.id!);
    heldCard.set(chat.id!, fields);
    while (heldCard.size > CACHE_LIMIT) heldCard.delete(heldCard.keys().next().value as string);
    const card = character?.card;
    if ((card?.desc?.trim() && !held.includes('card:desc'))
      || (card && before?.some((f) => f !== 'card:desc' && !fields.includes(f)
        && !!card[f.slice(5) as 'personality' | 'scenario']?.trim()))) refreshCharacter(chat.id!);
    if (!character?.card) return { held, snapshot: null }; // no scope for the entries yet: wait for the card
    const entries: CanonEntry[] = await within(Promise.all(texts.map(async (t) => {
      let hash = textHashes.get(t.text);
      if (hash) {
        textHashes.delete(t.text);
        textHashes.set(t.text, hash);
      } else {
        hash = await canonHash(t.text);
        if (t.text.length <= TEXT_HASH_SINGLE_MAX) {
          if (!textHashes.has(t.text)) textHashChars += t.text.length;
          textHashes.delete(t.text);
          textHashes.set(t.text, hash);
          while (textHashes.size > TEXT_HASH_LIMIT || (textHashes.size > 1 && textHashChars > TEXT_HASH_CHARS_LIMIT)) {
            const oldest = textHashes.keys().next().value as string;
            textHashes.delete(oldest);
            textHashChars -= oldest.length;
          }
        }
      }
      return { key: t.key, hash, metadata: t.metadata };
    })), deadline, 'the canon hashes');
    return { held, snapshot: { id: await canonManifestId(entries), entries, texts, observedAt: Date.now() } };
  }

  /** Sends the chat's canon when the sidecar does not have this manifest in force (ADR 0045): the manifest, then the
   *  texts it asks for, in batches. One upload per chat at a time, the newest waiting; background work after a
   *  request, never awaited, never throws. */
  function syncCanon(settings: Settings, conversationId: string, chatId: string, snapshot: CanonSnapshot): void {
    const key = `${settings.sidecarUrl}|${conversationId}`;
    if (canonUnsupported || canonSent.get(key) === snapshot.id) return;
    const queue = canonQueue.get(key) ?? { running: false, next: null };
    canonQueue.set(key, queue);
    if (queue.running) {
      queue.next = snapshot; // the newest observation wins; an older one waiting is dropped
      return;
    }
    queue.running = true;
    void (async () => {
      for (let current: CanonSnapshot | null = snapshot; current; current = queue.next, queue.next = null) {
        if (disposed || canonSent.get(key) === current.id) continue;
        try {
          if (await uploadCanon(settings, chatId, current)) {
            canonSent.set(key, current.id);
            while (canonSent.size > CACHE_LIMIT) canonSent.delete(canonSent.keys().next().value as string);
          }
        } catch (error) {
          const message = error instanceof Error ? error.message : String(error);
          if (/HTTP 404/.test(message) && !/conversation not found/.test(message)) canonUnsupported = true;
          host.debug('[NMOS] canon not synced:', message);
          if (canonUnsupported) break;
        }
      }
      queue.running = false;
      queue.next = null;
      if (canonQueue.get(key) === queue) canonQueue.delete(key);
    })();
  }

  /** One manifest upload: true once the sidecar has every text (applied, or a newer observation already in force). */
  async function uploadCanon(settings: Settings, chatId: string, snapshot: CanonSnapshot): Promise<boolean> {
    const texts = new Map(snapshot.entries.map((e, i) => [e.hash, snapshot.texts[i]!.text]));
    const deadline = host.now() + CANON_TIMEOUT_MS;
    const body = { host: 'pocketrisu', chat_id: chatId, entries: snapshot.entries, observed_at: snapshot.observedAt };
    let out = await call<{ needed: string[] }>(settings, '/v1/sync/canon', body, deadline);
    for (let round = 0; out.needed.length && round < CANON_ROUNDS; round++) {
      const contents: Record<string, string> = {};
      let size = 0;
      for (const h of out.needed) {
        const text = texts.get(h);
        // Batches of up to CANON_BATCH_CHARS; a longer text (up to MAX_CANON_CHARS) goes alone.
        if (text === undefined || (size && size + text.length > CANON_BATCH_CHARS)) continue;
        contents[h] = text;
        size += text.length;
      }
      out = await call<{ needed: string[] }>(settings, '/v1/sync/canon', { ...body, contents }, deadline);
    }
    return !out.needed.length;
  }

  /** Reads the host's personas in the background; a refusal or failure leaves the name unknown. */
  function warmPersonas(): void {
    if (!host.personas) return;
    personas = { value: personas?.value ?? null, at: host.now() };
    host.personas()
      .then((value) => { personas = { value, at: host.now() }; })
      .catch(() => { personas = { value: null, at: host.now() }; });
  }

  /** The persona name for this chat as last read; a stale or missing read is refreshed in the background. */
  function personaName(chat: HostChat): string | null {
    if (!personas || host.now() - personas.at > PERSONA_TTL_MS) warmPersonas();
    return personas?.value ? personaOf(chat, personas.value) : null;
  }

  function remember(key: string, packet: string, ttl: number, failed = false, memory: MemoryFit | null = null,
    vectors: Vectors | null = null, canon?: string, trim: TrimDecision | null = null,
    coverage: RecallCoverage | null = null, chatId?: string): void {
    cache.set(key, { packet, expires: host.now() + ttl, failed, memory, vectors, canon, trim, coverage, chatId });
    while (cache.size > CACHE_LIMIT) cache.delete(cache.keys().next().value as string);
  }

  /** Compact 128-bit streaming digest of a prompt's roles and contents (no full-prompt JSON string retained in RAM). */
  function promptSignature(prompt: PromptMessage[]): string | null {
    if (!Array.isArray(prompt)) return null;
    try {
      let h1 = 0x811c9dc5;
      let h2 = 0x9e3779b1;
      let h3 = 0x85ebca6b;
      let h4 = 0xc2b2ae35;
      let chars = 0;
      const mix = (code: number) => {
        h1 = Math.imul(h1 ^ code, 0x01000193) >>> 0;
        h2 = Math.imul(h2 ^ (code + 17), 0x85ebca6b) >>> 0;
        h3 = Math.imul(h3 ^ (code * 31 + 7), 0xc2b2ae35) >>> 0;
        h4 = Math.imul(h4 ^ ((code << 5) ^ (code >>> 2)), 0x27d4eb2f) >>> 0;
      };
      const feed = (s: string) => {
        chars += s.length;
        mix(s.length);
        for (let i = 0; i < s.length; i++) mix(s.charCodeAt(i));
      };
      for (let i = 0; i < prompt.length; i++) {
        const m = prompt[i];
        mix(0x1e);
        if (typeof m?.role === 'string') {
          mix(1);
          feed(m.role);
        } else {
          mix(0);
        }
        mix(0x1f);
        const c = m?.content;
        if (typeof c === 'string') {
          mix(2);
          feed(c);
        } else if (c == null) {
          mix(0);
        } else {
          mix(3);
          feed(JSON.stringify(c));
        }
      }
      return `${prompt.length}:${chars}:${h1.toString(16)}:${h2.toString(16)}:${h3.toString(16)}:${h4.toString(16)}`;
    } catch {
      return null;
    }
  }

  function isReturnedMemo(prompt: PromptMessage[], now: number): boolean {
    if (returnedMemo.size === 0) return false;
    const sig = promptSignature(prompt);
    if (sig === null) return false;
    const expires = returnedMemo.get(sig);
    if (expires === undefined) return false;
    if (expires <= now) {
      returnedMemo.delete(sig);
      return false;
    }
    return true;
  }

  function memoiseReturned(prompt: PromptMessage[]): void {
    const sig = promptSignature(prompt);
    if (sig === null) return;
    returnedMemo.delete(sig);
    returnedMemo.set(sig, host.now() + RETRY_MEMO_TTL_MS);
    while (returnedMemo.size > RETRY_MEMO_LIMIT) {
      returnedMemo.delete(returnedMemo.keys().next().value as string);
    }
  }

  /** Host work on the request path, cut at the deadline like a sidecar call: a host call that never answers
   *  must not hold the generation (fail open). The host call itself cannot be cancelled. */
  async function within<T>(work: Promise<T>, deadline: number, what: string): Promise<T> {
    const remaining = deadline - host.now();
    if (remaining <= 0) throw new DeadlineError(`deadline before ${what}`);
    let timer: ReturnType<typeof setTimeout> | undefined;
    const timeout = new Promise<never>((_, reject) => {
      timer = setTimeout(() => reject(new DeadlineError(`deadline during ${what}`)), remaining);
    });
    try {
      return await Promise.race([work, timeout]);
    } finally {
      clearTimeout(timer);
    }
  }

  /** `onLate`: when this call is cut at the deadline, called with the time its answer arrives anyway. */
  async function call<T>(settings: Settings, path: string, body: unknown, deadline: number,
                         method?: Method, onLate?: (at: number) => void): Promise<T> {
    const remaining = deadline - host.now();
    if (remaining <= 0) throw new DeadlineError(`deadline before ${path}`);
    const url = settings.sidecarUrl.replace(/\/+$/, '') + path;
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (settings.authToken) headers.Authorization = `Bearer ${settings.authToken}`;
    const verb = method ?? (body === undefined ? 'GET' : 'POST');
    const pending = host.request(verb, url, body, headers, remaining, settings.route);
    try {
      const res = await within(pending, deadline, path);
      if (res.status < 200 || res.status >= 300) {
        const detail = (res.json as { detail?: unknown } | null)?.detail;
        throw new Error(`${path} -> HTTP ${res.status}${detail ? `: ${Array.isArray(detail) ? detail.join('; ') : String(detail)}` : ''}`);
      }
      return res.json as T;
    } catch (error) {
      if (error instanceof DeadlineError && onLate) pending.then(() => onLate(host.now()), () => {});
      throw error;
    }
  }

  /** `rewritten`: how many of the bodies sent were replies the host rewrote after generating them (a trigger, Lua).
   *  `live`: checked before each step after the first; once false, the sync stops there (a background sync a request
   *  overtook, G6). */
  async function sync(settings: Settings, manifest: ReconcileRequest, bodies: Bodies, deadline: number,
                      live?: () => boolean) {
    const request = { ...manifest, plugin_build: PLUGIN_BUILD };  // the sidecar tells an outdated plugin (ADR 0037)
    let result = await call<ReconcileResult>(settings, '/v1/sync/reconcile', request, deadline);
    let rewritten = 0;
    if (result.status === 'needs_bodies') {
      const keys = (result.needed_bodies ?? []).map((n) => bodyKey(n.host_logical_id, n.revision_hash));
      rewritten = keys.filter((k) => bodies.rewritten(k)).length;
      const needed = keys.map((k) => bodies.get(k));
      if (needed.some((b) => !b)) throw new Error('sidecar asked for an unknown body');
      // Chunked so a first sync of a long chat makes durable progress even when it cannot finish
      // inside one request's deadline; the next request continues from what the sidecar stored.
      for (let i = 0; i < needed.length; i += BODY_CHUNK) {
        if (live && !live()) throw new Error('a newer request or reply came first');
        const last = i + BODY_CHUNK >= needed.length;
        const out = await call<{ ok: boolean; reconcile: ReconcileResult | null }>(settings, '/v1/sync/bodies', {
          host: 'pocketrisu', chat_id: request.chat_id, bodies: needed.slice(i, i + BODY_CHUNK),
          then_reconcile: last ? request : null,
        }, deadline);
        if (!out.ok) throw new Error('sidecar rejected bodies');
        if (last) {
          if (!out.reconcile) throw new Error('sidecar did not reconcile');
          result = out.reconcile;
        }
      }
    }
    if (result.status === 'needs_bodies') throw new Error('sidecar still needs bodies');
    return { ...result, rewritten };
  }

  async function prepare(prompt: PromptMessage[], mode: unknown): Promise<PromptMessage[]> {
    const started = host.now();
    const since = epoch;
    let settings: Settings | null = null;
    let key: string | null = null;
    let chatId: string | null = null;
    let announced = false;
    let failure: LastRequest | null = null;
    let lateAt: number | null = null;
    let k = 0; // recent turns kept when trimming (PHASE-60 S1); 0 = off
    const late = (at: number) => {
      lateAt = at;
      if (failure) failure.neededMs = Math.round(at - started);
    };
    try {
      if (mode !== 'model') return prompt; // aux request
      if (isReturnedMemo(prompt, started) || hasPacket(prompt)) return prompt; // retry of an injected prompt (H2)
      // The deadline is in the settings, so reading them has the default one.
      settings = await within(host.settings(), started + DEFAULT_DEADLINE_MS, 'the plugin settings');
      if (!settings.enabled || !settings.sidecarUrl) return prompt;
      // Without Web Crypto nothing can be hashed: say why in words instead of a TypeError (audit F24).
      if (!secureContext()) throw new Error(INSECURE_ERROR);
      const deadline = started + settings.deadlineMs;
      k = keepRecentTurnsOf(settings);
      emit({ type: 'request-start' });
      announced = true;

      const chat = await within(host.currentChat(), deadline, 'the host chat read');
      const messages: HostMessage[] = Array.isArray(chat?.message) ? chat!.message : [];
      if (!chat?.id) {
        emit({ type: 'request-abandon' });
        return prompt;
      }
      chatId = chat.id;
      // Switched off for this chat (ADR 0048): nothing of it is read further or sent, and no packet goes in.
      if (settings.offChats?.includes(chat.id)) {
        emit({ type: 'request-end', outcome: 'chat-off', chars: 0, conversationId: null });
        return prompt;
      }
      // A retry of a prompt whose packet a preset's placeholder put in a user block (H2): it is placed already.
      if (hasPacket(prompt, messages)) {
        emit({ type: 'request-abandon' });
        return prompt;
      }
      const turn = userTurnIndex(prompt, messages); // D13: the chat's latest user turn is in this prompt
      if (turn < 0) {
        // No memory without the turn to put it before; said where the owner looks, never silently (it was).
        const reason = 'the latest user message was not found in the prompt';
        host.warn('[NMOS] memory skipped for this request:', reason, { promptMessages: prompt.length,
          chatMessages: messages.length });
        last = { at: Date.now(), ms: Math.round(host.now() - started), packetChars: 0, packet: '', outcome: 'skipped',
          error: reason, deadlineMs: settings.deadlineMs };
        emit({ type: 'request-end', outcome: 'skipped', chars: 0, error: reason,
          conversationId: conversations.get(chat.id) ?? null });
        return prompt;
      }
      // A main request of this chat (a send, a reroll, a Continue) syncs it itself: the background sync after the last
      // reply is not needed, and one already running stops before its next step (G6). Only once its turn is found: an
      // auxiliary call in `model` mode (a script's own model call) leaves it.
      turnSeq++;
      cancelOutputSync();

      // `[NMOS.memory]` that a chat message itself holds (it mentions the placeholder) is not the preset's: placement
      // looks past it. Found again in a trimmed prompt, whose indices (and a copied message) differ.
      // The whole chat is cleaned once for this request, for the trimming pre-flight and the cut alike (finding 5).
      const scan = createTrimScan(prompt, messages);
      scan.turn = turn;
      const promptMatches = (scan.pairs = matchPromptToHost(prompt, messages));
      const chatMarkers = historyMarkerIndices(prompt, messages, promptMatches);
      const marker = findMarker(prompt, chatMarkers);
      const skipIn = (p: PromptMessage[]): Set<number> => (chatMarkers.size === 0 ? chatMarkers
        : p === prompt ? chatMarkers : historyMarkerIndices(p, messages));
      const position = settings.injectPosition;
      const after = landsAfterUserTurn(prompt, messages, position, turn, marker);
      const budget = after ? Math.max(0, settings.reservedMemoryTokens - GUARD_RESERVE_TOKENS) : settings.reservedMemoryTokens;
      // `at`: the latest user turn's index in `p` (the trimmed prompt's, once old dialogue is left out).
      // `held`: the prompt placed into holds the packet (placed now, or already there on a retry).
      const place = (p: PromptMessage[], packet: string, at: number): { out: PromptMessage[]; placed: boolean;
        held: boolean } => {
        if (!packet) return { out: stripMarkers(p), placed: false, held: false };
        const plain = packet.split(MEMORY_MARKER).join('');
        // The prompt already holds this packet (a retry), as placed: literal markers are removed from it on placement.
        if (holdsText(p, plain)) return { out: stripMarkers(p), placed: false, held: true };
        // The placeholder of the prompt placed into: a trimmed prompt may have left out the message that held it.
        const here = !marker ? null : p === prompt ? marker : findMarker(p, skipIn(p));
        const lands = here === marker ? after : landsAfterUserTurn(p, messages, position, at, here);
        let out = here ? resolvePlaceholders(p, lands ? withGuard(packet) : packet, skipIn(p)) : p;
        if (!holdsText(out, plain)) out = injectPacket(p, position === 'end' ? withGuard(packet) : packet, position, at);
        out = stripMarkers(out);
        const held = holdsText(out, plain);
        return { out, placed: held, held };
      };
      // Old dialogue is left out of the host's prompt (markers still in it) before the packet is placed, by the
      // sidecar's boundary (PHASE-60 S1, ADR 0083): never with no memory in its place. The final prompt is what a
      // retry (H2) sends back, so it is the one remembered. `refused`: the prompt cannot take the boundary, so the
      // packet (built as if the dialogue before it were gone) must not go in; the caller fetches one without a cut.
      const finishPrompt = (packet: string, decision: TrimDecision | null) => {
        let p = prompt;
        let dropped = 0;
        let savedTokens = 0;
        let reason = decision?.reason ?? null;
        let refused = false;
        if (decision?.keepFromId) {
          if (!packet) reason = 'empty_packet';
          else {
            const r = trimPrompt(prompt, messages, decision.keepFromId, scan);
            if (r.reason !== null) {
              refused = true;
              refusedTrim.delete(chat.id!);
              refusedTrim.set(chat.id!, { id: decision.keepFromId, at: host.now() });
              while (refusedTrim.size > CACHE_LIMIT) refusedTrim.delete(refusedTrim.keys().next().value as string);
              return { out: prompt, trim: { dropped: 0, savedTokens: 0, reason: r.reason, keepFromTurn: null }, refused };
            }
            p = r.prompt;
            dropped = r.dropped;
            savedTokens = r.savedTokens;
            reason = r.reason;
          }
        }
        const { out, placed, held } = place(p, packet, turn - dropped); // every dropped index is before `turn`
        // Never old dialogue left out with no memory in its place: treated as a refused cut (fetched again uncut).
        if (dropped > 0 && !held) {
          return { out: prompt, trim: { dropped: 0, savedTokens: 0, reason: 'format' as const, keepFromTurn: null },
            refused: true };
        }
        if (out !== prompt && (placed || dropped > 0)) memoiseReturned(out);
        const outcome: TrimOutcome = { dropped, savedTokens, reason,
          keepFromTurn: dropped > 0 ? decision?.keepFromTurn ?? null : null };
        return { out, trim: outcome, refused };
      };
      const shown = (o: TrimOutcome) => ({ dropped: o.dropped, savedTokens: o.savedTokens, reason: o.reason });

      // Cache key = exact chat state (every message id + revision hash) + prompt shape and the messages it holds + the
      // sidecar, route, token and budget it was asked with, so a cached packet is reused only for the same state (host retries, reroll of an unchanged
      // chat) and never survives an edit anywhere in the chat or a switch to another sidecar. The canon is checked
      // against the entry below (it is observed after the key).
      const t0 = host.now();
      const { request, bodies } = await within(buildManifest(chat, firstSaying(messages),
        { characterName: characterName(chat.id), personaName: personaName(chat) }), deadline, 'the manifest');
      const manifestMs = host.now() - t0;
      const inContext = inContextIds(prompt, messages, undefined, undefined, promptMatches);
      // Trimming asks the sidecar for a boundary only when the prompt can take a cut (PHASE-60 S1): a packet built for
      // a cut the prompt refuses would leave out of memory dialogue the prompt still holds, or send it twice. A
      // boundary refused before is not asked for again while the prompt still refuses it.
      const refusedAt = refusedTrim.get(chat.id);
      if (refusedAt && host.now() - refusedAt.at > REFUSED_TRIM_TTL_MS) refusedTrim.delete(chat.id);
      let askTrim = k > 0 && canTrimPrompt(prompt, messages, scan) && !(refusedAt && host.now() - refusedAt.at
        <= REFUSED_TRIM_TTL_MS && trimPrompt(prompt, messages, refusedAt.id, scan).reason !== null);
      // Internal key only (not a cross-language hash): plain JSON keeps it linear and cheap.
      // The token is hashed with the rest, never kept as it is.
      const keyOf = (withTrim: boolean) => within(sha256Hex(JSON.stringify([
        chat.id, mode, prompt.length, request.messages.map((m) => [m.host_logical_id, m.revision_hash]), inContext,
        request.persona_name ?? null, // the sidecar reads `{{user}}` from the sync a cached packet skips (ADR 0023)
        settings!.sidecarUrl.replace(/\/+$/, ''), settings!.route, settings!.authToken, budget,
        !!settings!.trimOldTurns, k, withTrim,
      ])), deadline, 'the cache key');
      key = await keyOf(askTrim);
      // Canon (ADR 0045): which of it this prompt holds and its manifest go with the request; the texts follow in the
      // background. Observed for a cached packet too, whose canon may have changed.
      const canon = await observeCanon(chat, prompt, deadline);
      const canonKey = JSON.stringify([canon?.snapshot?.id ?? null, canon?.held ?? []]);
      // A packet built with other canon (an entry, the card or the note edited) is stale; a cached miss holds none.
      const lookup = (at: string) => {
        const entry = cache.get(at);
        return { cached: entry, hit: entry && entry.expires > host.now() && (entry.failed || entry.canon === canonKey)
          ? finishPrompt(entry.packet, k > 0 ? (entry.failed ? FAILED_TRIM : entry.trim ?? FAILED_TRIM) : null) : null };
      };
      let { cached, hit } = lookup(key);
      // A cached boundary this prompt refuses (the same state, another layout): no boundary is asked for in this
      // request; the packet without a cut is served from the cache, else fetched below and kept (a failure too) under
      // the key the next request will have.
      if (hit?.refused) {
        cache.delete(key);
        askTrim = false;
        key = await keyOf(false);
        ({ cached, hit } = lookup(key));
      }
      if (cached && hit && !hit.refused) {
        const known = conversations.get(chat.id);
        if (canon?.snapshot && known) syncCanon(settings, known, chat.id, canon.snapshot);
        const outcome = cached.packet ? 'injected' : 'nothing-relevant';
        const done = hit;
        // A retry served from the miss cache keeps the failure on the status tab.
        if (!cached.failed) last = { at: Date.now(), ms: Math.round(host.now() - started), packetChars: cached.packet.length,
          packet: cached.packet, outcome, deadlineMs: settings.deadlineMs, budgetTokens: budget,
          memory: cached.memory ?? null, vectors: cached.vectors ?? null,
          ...(k > 0 ? { trim: done.trim } : {}), ...(cached.coverage ? { coverage: cached.coverage } : {}) };
        emit({ type: 'request-end', outcome, chars: cached.packet.length, reused: true, vectors: cached.vectors ?? null,
          conversationId: conversations.get(chat.id) ?? null, ...(k > 0 ? { trim: shown(done.trim) } : {}) });
        return done.out;
      }

      // A background sync of this chat that is still running (G6) may apply after this sync: the head would then move
      // past the commit recall is asked for. It is given a moment to end first, within the deadline.
      if (outputRunning?.chatId === chat.id) await settleWithin(outputRunning.done,
        Math.min(OUTPUT_SYNC_WAIT_MS, (deadline - host.now()) / 2));
      // A drop of this chat's packets from here on (its memory moved) means this packet may be from before it.
      const dropsBefore = dropSeq;
      const t1 = host.now();
      const synced = await sync(settings, request, bodies, deadline);
      const syncMs = host.now() - t1;
      noteSynced(chat.id, messages.length);
      if (synced.conversation_id) {
        conversations.delete(chat.id);
        conversations.set(chat.id, synced.conversation_id);
        while (conversations.size > CACHE_LIMIT) conversations.delete(conversations.keys().next().value as string);
      }

      // A Continue asks with the reply it continues (G7); the request to the sidecar is the same shape.
      const { query, previousAi, isContinue } = queryTexts(messages);
      if (isContinue) host.debug('[NMOS] continue: recall asks with the reply being continued');
      const t2 = host.now();
      const retrieve = (withTrim: boolean) => call<{ freshness: string; packet: { text: string };
        memory?: MemoryFit | null; vectors?: Vectors | null; trim?: unknown; coverage?: unknown }>(settings!, '/v1/retrieve', {
        host: 'pocketrisu',
        chat_id: chat.id,
        active_commit: synced.active_commit,
        manifest_hash: synced.manifest_hash,
        query,
        previous_ai: previousAi,
        in_context_ids: inContext,
        budget_tokens: budget,
        client_timings_ms: { manifest: manifestMs, sync: syncMs, before_retrieve: t2 - started },
        canon_manifest_id: canon?.snapshot?.id ?? null,
        canon_held: canon?.held ?? [],
        // Only when the owner turned trimming on and the prompt can take a cut: otherwise the request is the one sent
        // before PHASE-60.
        ...(withTrim ? { trim: { keep_recent_turns: k, step: k } } : {}),
      }, deadline, undefined, late);
      let retrieved = await retrieve(askTrim);
      if (canon?.snapshot && synced.conversation_id) syncCanon(settings, synced.conversation_id, chat.id, canon.snapshot);
      const answer = (r: typeof retrieved, withTrim: boolean) => {
        const fresh = r.freshness === 'fresh';
        return { packet: fresh ? r.packet.text : '', memory: fresh ? r.memory ?? null : null, // older sidecars send none
          vectors: fresh ? r.vectors ?? null : null, coverage: coverageOf(r.coverage),
          decision: k > 0 ? (withTrim ? trimDecisionOf(fresh, r.trim) : FORMAT_TRIM) : null };
      };
      let got = answer(retrieved, askTrim);
      // A delete, repair or settings save while this request ran: its packet may hold what that removed.
      if (epoch !== since) throw new Error('memory changed during this request');
      let done = finishPrompt(got.packet, got.decision);
      if (done.refused) {
        // The prompt cannot take the sidecar's boundary: its packet left out of memory dialogue the prompt still
        // holds. Never placed; the packet for the whole prompt is fetched once within the same deadline (a failure or
        // the deadline fails open like any other), and kept under the key the next request will have.
        key = await keyOf(false);
        retrieved = await retrieve(false);
        got = answer(retrieved, false);
        if (epoch !== since) throw new Error('memory changed during this request');
        done = finishPrompt(got.packet, got.decision);
      }
      const { packet, memory, vectors, decision, coverage } = got;
      // A non-fresh answer (`stale`: the head moved past the commit asked for) is not an empty packet: not remembered.
      if (retrieved.freshness === 'fresh' && (droppedAt.get(chat.id) ?? 0) <= dropsBefore) {
        remember(key, packet, packet ? SUCCESS_TTL_MS : EMPTY_TTL_MS, false, memory, vectors, canonKey, decision,
          coverage, chat.id);
      }
      host.debug('[NMOS] request done', { ms: Math.round(host.now() - started), manifestMs: Math.round(manifestMs),
        syncMs: Math.round(syncMs), retrieveMs: Math.round(host.now() - t2), packetChars: packet.length });
      const outcome = packet ? 'injected' : 'nothing-relevant';
      last = { at: Date.now(), ms: Math.round(host.now() - started), packetChars: packet.length, packet, outcome,
        deadlineMs: settings.deadlineMs, budgetTokens: budget, memory, vectors,
        ...(k > 0 ? { trim: done.trim } : {}), ...(coverage ? { coverage } : {}) };
      emit({ type: 'request-end', outcome, chars: packet.length, vectors, conversationId: synced.conversation_id ?? null,
        ...(synced.rewritten > 0 ? { rewritten: synced.rewritten } : {}), ...(k > 0 ? { trim: shown(done.trim) } : {}) });
      return done.out;
    } catch (error) {
      // Cache the miss briefly so host retries of this request (H2) do not wait out the deadline again.
      if (key && epoch === since) remember(key, '', FAILURE_TTL_MS, true);
      last = failure = { at: Date.now(), ms: Math.round(host.now() - started), packetChars: 0, packet: '', outcome: 'failed',
        error: error instanceof Error ? error.message : String(error), deadlineMs: settings?.deadlineMs ?? 0,
        // Nothing is left out on any failure: the host's prompt goes as it is.
        ...(k > 0 ? { trim: { dropped: 0, savedTokens: 0, reason: 'failed', keepFromTurn: null } } : {}) };
      if (lateAt !== null) failure.neededMs = Math.round(lateAt - started);
      if (announced) emit({ type: 'request-end', outcome: 'failed', chars: 0, error: last.error,
        deadlineMs: last.deadlineMs, conversationId: (chatId && conversations.get(chatId)) || null,
        ...(k > 0 ? { trim: { dropped: 0, savedTokens: 0, reason: 'failed' } } : {}) });
      host.warn('[NMOS] memory skipped for this request (fail open):', error instanceof Error ? error.message : error);
      return prompt;
    }
  }

  /** Every path out of `beforeRequest` strips any remaining `[NMOS.memory]` literal (ADR 0083). */
  async function beforeRequest(prompt: PromptMessage[], mode: unknown): Promise<PromptMessage[]> {
    // The background sync after the last reply (G6) is cancelled in `prepare`, once the request's turn is found.
    try {
      return stripMarkers(await prepare(prompt, mode));
    } catch {
      return stripMarkers(prompt);
    }
  }

  function cancelOutputSync(): void {
    if (outputTimer === null) return;
    try { clearTimer(outputTimer); } catch { /* a timer that cannot be cleared finds `turnSeq` moved on */ }
    outputTimer = null;
  }

  /** Syncs chat `chatId` in the background once the wait after its reply is over (G6), so the reply is in memory (and
   *  can be extracted) before the next message, and the panel's Author's Note, Carry and Inspector see it. Replaces a
   *  waiting one; never throws. */
  function scheduleOutputSync(chatId: string, seen: number, replyId: string, replyLength: number): void {
    cancelOutputSync();
    if (!(outputSyncMs > 0) || disposed) return;
    try {
      const handle = setTimer(() => {
        if (outputTimer === handle) outputTimer = null;
        const done = outputSync(chatId, seen, replyId, replyLength);
        const running = { chatId, done };
        outputRunning = running;
        void done.finally(() => { if (outputRunning === running) outputRunning = null; });
      }, outputSyncMs);
      outputTimer = handle;
    } catch (error) {
      host.debug('[NMOS] background sync not scheduled:', error instanceof Error ? error.message : error);
    }
  }

  /** The sync a request would make, of the chat as it is now: the `output` snapshot is provisional (H7), and the chat
   *  read now must still be the one replied in (there is no hook for a chat switch). It must also still be the chat
   *  itself: a snapshot without reply `replyId`, or shorter than the plugin last synced, may be a chat still loading
   *  (HOST-FACTS Q8 item 7) whose manifest would retract the head. And the chat as the reply left it: one that grew
   *  past the `replyLength` messages it had then, or is streaming, has a newer turn on its way (a send whose request
   *  went without memory) and a reply half written. On doubt nothing is sent, and the next request syncs as always. */
  async function outputSync(chatId: string, seen: number, replyId: string, replyLength: number): Promise<void> {
    const live = () => turnSeq === seen;
    try {
      const settings = await host.settings();
      if (!live() || !settings.enabled || !settings.sidecarUrl || settings.offChats?.includes(chatId) || !secureContext()
        || !outputOn(settings)) return;  // the switch turned off (or another sidecar set) while it waited
      const chat = await host.currentChat();
      if (!live() || !chat?.id || chat.id !== chatId) return;  // another chat is open: its own next request syncs it
      const messages: HostMessage[] = Array.isArray(chat.message) ? chat.message : [];
      if (!messages.some((m) => m?.chatId === replyId) || messages.length < (syncedLength.get(chatId) ?? 0)
        || messages.length > replyLength || chat.isStreaming === true) {
        host.debug('[NMOS] background sync skipped: the chat read is not the one replied in', {
          messages: messages.length, synced: syncedLength.get(chatId) ?? null });
        return;
      }
      const deadline = host.now() + OUTPUT_SYNC_TIMEOUT_MS;
      const { request, bodies } = await within(buildManifest(chat, firstSaying(messages),
        { characterName: characterName(chat.id), personaName: personaName(chat) }), deadline, 'the manifest');
      if (!live()) return;
      // A packet cached for this chat is not reused once the ledger holds the reply: a reroll removes it from the chat
      // before its request (H14), and a reroll served from the cache would skip the sync that takes it out again.
      dropChatPackets(chatId);
      const synced = await sync(settings, { ...request, trigger: 'output' }, bodies, deadline, live);
      noteSynced(chatId, messages.length);
      if (synced.conversation_id) {
        conversations.delete(chatId);
        conversations.set(chatId, synced.conversation_id);
        while (conversations.size > CACHE_LIMIT) conversations.delete(conversations.keys().next().value as string);
      }
      // Again: a packet remembered while the sync ran may be of the chat without what it applied.
      dropChatPackets(chatId);
      host.debug('[NMOS] reply synced in the background', { status: synced.status });
    } catch (error) {
      host.debug('[NMOS] background sync after the reply failed:', error instanceof Error ? error.message : error);
    }
  }

  function noteSynced(chatId: string, length: number): void {
    syncedLength.delete(chatId);
    syncedLength.set(chatId, length);
    while (syncedLength.size > CACHE_LIMIT) syncedLength.delete(syncedLength.keys().next().value as string);
  }

  /** Waits for `work` (which never rejects) up to `ms`; never throws. */
  async function settleWithin(work: Promise<void>, ms: number): Promise<void> {
    if (!(ms > 0)) return;
    let timer: ReturnType<typeof setTimeout> | undefined;
    await Promise.race([work, new Promise<void>((resolve) => { timer = setTimeout(resolve, ms); })]);
    clearTimeout(timer);
  }

  function dropChatPackets(chatId: string): void {
    for (const [k, entry] of cache) if (entry.chatId === chatId) cache.delete(k);
    droppedAt.delete(chatId);
    droppedAt.set(chatId, ++dropSeq);
    while (droppedAt.size > CACHE_LIMIT) droppedAt.delete(droppedAt.keys().next().value as string);
  }

  /** A coverage answer for conversation `conversationId`: once what its memory holds is not what it was (or first
   *  seen, with nothing to compare), the packets cached for its chats are dropped. A reroll of an unchanged chat then
   *  asks again instead of reusing a packet built before an extraction finished. */
  function noteCoverage(conversationId: string, answer: unknown): void {
    const mark = memoryMark(answer);
    if (mark === null || coverageMarks.get(conversationId) === mark) return;
    coverageMarks.delete(conversationId);
    coverageMarks.set(conversationId, mark);
    while (coverageMarks.size > CACHE_LIMIT) coverageMarks.delete(coverageMarks.keys().next().value as string);
    for (const [chatId, id] of conversations) if (id === conversationId) dropChatPackets(chatId);
  }

  /** Whether the sidecar now set extracts a reply right after it, as last read from it. */
  function outputOn(settings: Settings): boolean {
    return outputSwitch?.url === sidecarKey(settings) && outputSwitch.on === true;
  }

  /** Remembers the switch from the answer of `/v1/config` request number `seq` (`null`: it failed or its answer is
   *  unknown), unless a newer answer was noted, or it is a read that started before a save answered. */
  function noteConfig(settings: Settings, seq: number, save: boolean, config: unknown | null): void {
    if (save) {
      configFence = Math.max(configFence, configStarted);
      if (seq < configSaved) return;
      configSaved = seq;
    } else if (seq < configNoted || seq <= configFence) {
      return;
    }
    configNoted = Math.max(configNoted, seq);
    outputSwitch = { url: sidecarKey(settings), on: config === null ? null : outputSwitchOf(config) };
  }

  /** Reads the sidecar's settings for the switch; never throws. Not while NMOS is off: nothing reaches the sidecar. */
  async function readConfig(): Promise<void> {
    let settings: Settings | null = null;
    let seq = 0;
    try {
      settings = await host.settings();
      if (!settings.enabled || !settings.sidecarUrl) return;
      seq = ++configStarted;
      noteConfig(settings, seq, false,
        await call<unknown>(settings, '/v1/config', undefined, host.now() + CONFIG_TIMEOUT_MS, 'GET'));
    } catch (error) {
      if (settings?.sidecarUrl && seq) noteConfig(settings, seq, false, null);
      host.debug('[NMOS] sidecar settings not read:', error instanceof Error ? error.message : error);
    }
  }

  /** At load (after the hooks): reads the switch now and again every `CONFIG_REFRESH_MS`, in the background. */
  function warmConfig(): void {
    if (refreshing || disposed) return;
    refreshing = true;
    const next = (): void => {
      if (disposed) return;
      try {
        refreshHandle = setRefreshTimer(() => {
          refreshHandle = null;
          if (disposed) return;
          void readConfig().finally(next);
        }, CONFIG_REFRESH_MS);
      } catch (error) {
        refreshing = false;
        host.debug('[NMOS] sidecar settings refresh not scheduled:', error instanceof Error ? error.message : error);
      }
    };
    void readConfig().finally(next);
  }

  /** The plugin is unloaded or re-imported (the host's `onUnload`, where it has one): the 5-minute read of the
   *  sidecar's settings and a waiting background sync are cleared, and neither is set again; a sync already running
   *  stops before its next step. Never throws. */
  function dispose(): void {
    disposed = true;
    turnSeq++;
    cancelOutputSync();
    if (refreshHandle !== null) {
      try { clearTimer(refreshHandle); } catch { /* the chain finds `disposed` set when it fires */ }
      refreshHandle = null;
    }
    cache.clear();
    returnedMemo.clear();
    conversations.clear();
    names.clear();
    canonSent.clear();
    canonQueue.clear();
    textHashes.clear();
    textHashChars = 0;
    heldCard.clear();
    refusedTrim.clear();
    droppedAt.clear();
    coverageMarks.clear();
    syncedLength.clear();
    buildManifest.clear();
    personas = null;
    last = null;
  }

  /** Output listener: provisional hint only (H7), and the background sync after the reply (G6). Never awaited work,
   *  never throws. */
  function onOutput(arg: { chat?: HostChat; messageIndex?: number }): void {
    const seen = ++turnSeq;
    cancelOutputSync();
    void (async () => {
      const settings = await host.settings();
      if (!settings.enabled || !settings.sidecarUrl || !arg?.chat?.id || settings.offChats?.includes(arg.chat.id)) return;
      // Scheduled first: whatever happens to the notification below, the reply is synced. Only when the sidecar
      // extracts a reply right after it: otherwise the sync would only cost (and a request could wait on it).
      // The reply's id goes with it: a chat read later that does not hold it is not synced (no id: never scheduled).
      const index = arg.messageIndex ?? -1;
      const message = index >= 0 ? arg.chat.message?.[index] : undefined;
      if (turnSeq === seen && outputOn(settings) && typeof message?.chatId === 'string' && message.chatId) {
        scheduleOutputSync(arg.chat.id, seen, message.chatId, arg.chat.message!.length);
      }
      // A reply is extracted after it (H7): an empty packet cached for this chat may have memory now. A packet with
      // memory stays for a reroll of an unchanged chat until the background sync has the reply.
      for (const [k, entry] of cache) if (entry.chatId === arg.chat.id && !entry.packet && !entry.failed) cache.delete(k);
      adviseOnce(settings.language);
      reachOnce(settings.language, settings.sidecarUrl);
      emit({ type: 'background', conversationId: conversations.get(arg.chat.id) ?? null });
      await call(settings, '/v1/output', {
        host: 'pocketrisu',
        chat_id: arg.chat.id,
        host_logical_id: message?.chatId ?? null,
        generation_id: message?.generationInfo?.generationId ?? null,
        revision_hash: message ? await sha256Hex(canonicalJson(hashPayload(message))) : null,
        message_index: index,
      }, host.now() + settings.deadlineMs);
    })().catch((error) => host.debug('[NMOS] output notification failed:', error instanceof Error ? error.message : error));
  }

  /**
   * Once per page, after a reply that went without memory because recall missed the deadline, say so in
   * the host's dialog with the value to set (owner decision on audit A-09). The panel keeps the advice.
   */
  let alerted = false;
  function adviseOnce(lang: Lang): void {
    const advice = deadlineAdvice(last);
    if (alerted || !host.alert || advice?.level !== 'over') return;
    alerted = true;
    const took = advice.tookMs === null ? '' : t(lang, 'deadline.took', { n: formatMs(advice.tookMs) });
    host.alert(t(lang, 'deadline.alert', { d: formatMs(advice.deadlineMs), took, s: formatMs(advice.suggestMs) }));
  }

  /**
   * Once per page, after a reply that went without memory because NMOS could not be reached (stopped, a wrong address
   * or token, a refused host, an insecure page), say so in the host's dialog (pre-0.4.0 audit F25): with default
   * settings nothing else in the chat shows it.
   */
  let reachAlerted = false;
  function reachOnce(lang: Lang, url: string): void {
    const kind = last?.outcome === 'failed' ? failureKind(last.error) : null;
    if (reachAlerted || !host.alert || !kind || kind === 'deadline' || kind === 'other') return;
    reachAlerted = true;
    host.alert(t(lang, `reach.${kind}` as StringKey, { url: url.replace(/\/+$/, '') }));
  }

  /** Human-readable status for the settings menu (Korean first, English second). */
  async function status(): Promise<StatusInfo> {
    const settings = await host.settings();
    const info: StatusInfo = { enabled: settings.enabled, sidecarUrl: settings.sidecarUrl, language: settings.language,
      connected: false, last, insecure: !secureContext() };
    try {
      const res = await call<{ version: string; features: Record<string, boolean>; plugin?: { expected: string | null };
        install?: string | null }>(settings, '/v1/health', undefined, host.now() + 3000);
      Object.assign(info, { connected: true, version: res.version, features: res.features ?? {},
        pluginExpected: res.plugin?.expected ?? null, install: res.install ?? null });
    } catch (error) {
      info.error = error instanceof Error ? error.message : String(error);
    }
    return info;
  }

  /** Sidecar API for the settings UI (longer timeout: connection tests call real models). */
  async function api<T>(method: Method, path: string, body?: unknown, timeoutMs = 90_000): Promise<T> {
    const settings = await host.settings();
    // A settings save, rebuild or delete changes what a packet would contain: a reroll of an unchanged chat must not
    // reuse a packet built before it (a deleted chat's memory, old facts), nor one fetched while it ran. Also when the
    // answer failed or came after the timeout: the sidecar may have applied it, or apply it then.
    const change = method !== 'GET';
    // The panel's reads and saves of the sidecar's settings carry the switch for the background sync (G6): a save
    // is in force at once. One that failed may or may not have been applied: not known until the next read.
    const config = path === '/v1/config' && (method === 'GET' || method === 'PUT');
    const covered = method === 'GET' ? COVERAGE_PATH.exec(path)?.[1] : undefined;
    const seq = config ? ++configStarted : 0;
    if (change) invalidate();
    try {
      const out = await call<T>(settings, path, body, host.now() + timeoutMs, method, change ? invalidate : undefined);
      if (config) noteConfig(settings, seq, method === 'PUT', out);
      if (covered) noteCoverage(covered, out);  // a conversation id (a UUID), as the HUD and panel put it in the path
      return out;
    } catch (error) {
      if (config) noteConfig(settings, seq, method === 'PUT', null);
      throw error;
    } finally {
      if (change) invalidate();
    }
  }

  /** A file from the sidecar (an archive, ADR 0050), as bytes; an error answer throws with the sidecar's detail. */
  async function file(path: string, timeoutMs = 300_000): Promise<ArrayBuffer> {
    if (!host.requestFile) throw new Error('this host cannot fetch a file');
    const settings = await host.settings();
    const headers: Record<string, string> = {};
    if (settings.authToken) headers.Authorization = `Bearer ${settings.authToken}`;
    const res = await host.requestFile(settings.sidecarUrl.replace(/\/+$/, '') + path, headers, timeoutMs, settings.route);
    if (res.status < 200 || res.status >= 300 || !res.bytes) {
      const detail = (res.json as { detail?: unknown } | null)?.detail;
      throw new Error(`${path.split('?')[0]} -> HTTP ${res.status}${detail ? `: ${String(detail)}` : ''}`);
    }
    return res.bytes;
  }

  return { beforeRequest, onOutput, status, api, file, warmPersonas, warmConfig, dispose };
}

const CARD_FIELDS = ['card:desc', 'card:personality', 'card:scenario'];

function firstSaying(messages: HostMessage[]): string | null {
  for (const m of messages) if (m.role === 'char' && m.saying) return m.saying;
  return null;
}
