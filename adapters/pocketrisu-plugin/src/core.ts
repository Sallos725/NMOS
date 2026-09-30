// Request-path orchestration. Host access comes in through `HostPort`; everything fails open.

import type { MemoryFit } from './budget';
import { PLUGIN_BUILD } from './build';
import { canonHash, canonManifestId, canonTexts, heldKeys, type CanonEntry, type CanonText, type HostCard, type HostLoreEntry,
  type HostPersona } from './canon';
import { canonicalJson } from './canonical';
import { sha256Hex } from './hash';
import { deadlineAdvice, formatMs } from './deadline';
import { DEFAULT_DEADLINE_MS } from './form';
import { t, type Lang } from './i18n';
import { bodyKey, createManifestBuilder, hashPayload, type Bodies } from './manifest';
import type { ActivityEvent } from './hud';
import { hasPacket, inContextIds, injectPacket, queryTexts, userTurnIndex, type InjectPosition } from './prompt';
import type { HostChat, HostMessage, HostPersonas, PromptMessage, ReconcileRequest } from './types';

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
  request(method: 'GET' | 'POST' | 'PUT', url: string, body: unknown, headers: Record<string, string>,
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
}

/** Whether the sidecar's recall searched vectors (PHASE-15 Q5, K34): "fallback" is lexical only because the embedder
 *  failed or did not answer in time. Older sidecars send none. */
export type Vectors = 'on' | 'off' | 'fallback';

const SUCCESS_TTL_MS = 10 * 60_000;
const FAILURE_TTL_MS = 30_000;
const CACHE_LIMIT = 64;
const BODY_CHUNK = 250;

export interface LastRequest {
  at: number;
  ms: number;
  packetChars: number;
  /** The memory text this request carried, for the status tab; kept in memory only. */
  packet: string;
  outcome: 'injected' | 'nothing-relevant' | 'failed';
  error?: string;
  /** The deadline this request had. */
  deadlineMs: number;
  /** Cut at the deadline, but recall answered later: how long the whole request took (audit A-09). */
  neededMs?: number;
  /** The memory budget this request had, and what it left out (ADR 0036). */
  budgetTokens?: number;
  memory?: MemoryFit | null;
  vectors?: Vectors | null;
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
}

const NAME_TTL_MS = 10 * 60_000;
const CANON_TIMEOUT_MS = 30_000;
const CANON_ROUNDS = 20;
const CANON_BATCH_CHARS = 800_000; // texts per canon call (a lorebook can hold 400k+ characters)
const TEXT_HASH_LIMIT = 4000;

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
const PERSONA_TTL_MS = 30_000; // a persona switch reaches the sidecar within this (it is re-read in the background)

/** The persona the host uses for `{{user}}` in this chat: the chat-bound one, else the selected one. */
export function personaOf(chat: HostChat, host: HostPersonas): string | null {
  const list = Array.isArray(host.personas) ? host.personas : [];
  const bound = chat.bindedPersona ? list.find((p) => p?.id === chat.bindedPersona) : undefined;
  const name = (bound ?? list[host.selected])?.name;
  return typeof name === 'string' && name.trim() ? name.trim() : null;
}

/** `onActivity` feeds the progress display (D28): called synchronously, never awaited, errors ignored. */
export function createAdapter(host: HostPort, onActivity?: (event: ActivityEvent) => void) {
  const cache = new Map<string, CacheEntry>();
  const conversations = new Map<string, string>(); // host chat id → sidecar conversation id
  const names = new Map<string, { name: string | null; card: HostCard | null; at: number }>();
  const canonSent = new Map<string, string>(); // sidecar + conversation → the manifest id the sidecar has in force
  const canonQueue = new Map<string, { running: boolean; next: CanonSnapshot | null }>(); // one upload per chat at a time
  const textHashes = new Map<string, string>(); // canon text → its hash (texts rarely change: hashed once)
  let canonUnsupported = false; // an older sidecar has no /v1/sync/canon
  let personas: { value: HostPersonas | null; at: number } | null = null;
  const buildManifest = createManifestBuilder();
  let last: LastRequest | null = null;
  let epoch = 0; // bumped by every panel change: a request that saw another epoch neither caches nor injects

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

  /** Reads the chat's bot (its name and, with `card`, its card) in the background. */
  function refreshCharacter(chatId: string): void {
    const hit = names.get(chatId);
    names.set(chatId, { name: hit?.name ?? null, card: hit?.card ?? null, at: host.now() });
    if (host.card) {
      host.card(chatId)
        .then((card) => {
          if (card) names.set(chatId, { name: card.name?.trim() || null, card, at: host.now() });
        })
        .catch(() => {});
    } else if (host.characterName) {
      host.characterName(chatId)
        .then((name) => { if (name) names.set(chatId, { name, card: null, at: host.now() }); })
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
    // The card's description is in every prompt (H19): missing, the card was edited since it was read.
    if (character?.card?.desc?.trim() && !held.includes('card:desc')) refreshCharacter(chat.id!);
    if (!character?.card) return { held, snapshot: null }; // no scope for the entries yet: wait for the card
    const entries: CanonEntry[] = await within(Promise.all(texts.map(async (t) => {
      let hash = textHashes.get(t.text);
      if (!hash) {
        hash = await canonHash(t.text);
        textHashes.set(t.text, hash);
        while (textHashes.size > TEXT_HASH_LIMIT) textHashes.delete(textHashes.keys().next().value as string);
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
        if (canonSent.get(key) === current.id) continue;
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
    vectors: Vectors | null = null, canon?: string): void {
    cache.set(key, { packet, expires: host.now() + ttl, failed, memory, vectors, canon });
    while (cache.size > CACHE_LIMIT) cache.delete(cache.keys().next().value as string);
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
                         method?: 'GET' | 'POST' | 'PUT', onLate?: (at: number) => void): Promise<T> {
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

  async function sync(settings: Settings, manifest: ReconcileRequest, bodies: Bodies, deadline: number) {
    const request = { ...manifest, plugin_build: PLUGIN_BUILD };  // the sidecar tells an outdated plugin (ADR 0037)
    let result = await call<ReconcileResult>(settings, '/v1/sync/reconcile', request, deadline);
    if (result.status === 'needs_bodies') {
      const needed = (result.needed_bodies ?? []).map((n) => bodies.get(bodyKey(n.host_logical_id, n.revision_hash)));
      if (needed.some((b) => !b)) throw new Error('sidecar asked for an unknown body');
      // Chunked so a first sync of a long chat makes durable progress even when it cannot finish
      // inside one request's deadline; the next request continues from what the sidecar stored.
      for (let i = 0; i < needed.length; i += BODY_CHUNK) {
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
    return result;
  }

  async function beforeRequest(prompt: PromptMessage[], mode: unknown): Promise<PromptMessage[]> {
    const started = host.now();
    const since = epoch;
    let settings: Settings | null = null;
    let key: string | null = null;
    let chatId: string | null = null;
    let announced = false;
    let failure: LastRequest | null = null;
    let lateAt: number | null = null;
    const late = (at: number) => {
      lateAt = at;
      if (failure) failure.neededMs = Math.round(at - started);
    };
    try {
      if (mode !== 'model' || hasPacket(prompt)) return prompt; // aux request, or retry of an injected prompt (H2)
      // The deadline is in the settings, so reading them has the default one.
      settings = await within(host.settings(), started + DEFAULT_DEADLINE_MS, 'the plugin settings');
      if (!settings.enabled || !settings.sidecarUrl) return prompt;
      const deadline = started + settings.deadlineMs;
      emit({ type: 'request-start' });
      announced = true;

      const chat = await within(host.currentChat(), deadline, 'the host chat read');
      const messages: HostMessage[] = Array.isArray(chat?.message) ? chat!.message : [];
      const turn = userTurnIndex(prompt, messages); // D13: the chat's latest user turn is in this prompt
      if (!chat?.id || turn < 0) {
        emit({ type: 'request-abandon' });
        return prompt;
      }
      chatId = chat.id;
      // Switched off for this chat (ADR 0048): nothing of it is read further or sent, and no packet goes in.
      if (settings.offChats?.includes(chat.id)) {
        emit({ type: 'request-end', outcome: 'chat-off', chars: 0, conversationId: null });
        return prompt;
      }

      // Cache key = exact chat state (every message id + revision hash) + prompt shape and the messages it holds + the
      // sidecar, route, token and budget it was asked with, so a cached packet is reused only for the same state (host retries, reroll of an unchanged
      // chat) and never survives an edit anywhere in the chat or a switch to another sidecar. The canon is checked
      // against the entry below (it is observed after the key).
      const t0 = host.now();
      const { request, bodies } = await within(buildManifest(chat, firstSaying(messages),
        { characterName: characterName(chat.id), personaName: personaName(chat) }), deadline, 'the manifest');
      const manifestMs = host.now() - t0;
      const inContext = inContextIds(prompt, messages);
      // Internal key only (not a cross-language hash): plain JSON keeps it linear and cheap.
      // The token is hashed with the rest, never kept as it is.
      key = await within(sha256Hex(JSON.stringify([
        chat.id, mode, prompt.length, request.messages.map((m) => [m.host_logical_id, m.revision_hash]), inContext,
        request.persona_name ?? null, // the sidecar reads `{{user}}` from the sync a cached packet skips (ADR 0023)
        settings.sidecarUrl.replace(/\/+$/, ''), settings.route, settings.authToken, settings.reservedMemoryTokens,
      ])), deadline, 'the cache key');
      // Canon (ADR 0045): which of it this prompt holds and its manifest go with the request; the texts follow in the
      // background. Observed for a cached packet too, whose canon may have changed.
      const canon = await observeCanon(chat, prompt, deadline);
      const canonKey = JSON.stringify([canon?.snapshot?.id ?? null, canon?.held ?? []]);
      const cached = cache.get(key);
      // A packet built with other canon (an entry, the card or the note edited) is stale; a cached miss holds none.
      if (cached && cached.expires > host.now() && (cached.failed || cached.canon === canonKey)) {
        const known = conversations.get(chat.id);
        if (canon?.snapshot && known) syncCanon(settings, known, chat.id, canon.snapshot);
        const outcome = cached.packet ? 'injected' : 'nothing-relevant';
        // A retry served from the miss cache keeps the failure on the status tab.
        if (!cached.failed) last = { at: Date.now(), ms: Math.round(host.now() - started), packetChars: cached.packet.length,
          packet: cached.packet, outcome, deadlineMs: settings.deadlineMs, budgetTokens: settings.reservedMemoryTokens,
          memory: cached.memory ?? null, vectors: cached.vectors ?? null };
        emit({ type: 'request-end', outcome, chars: cached.packet.length, reused: true, vectors: cached.vectors ?? null,
          conversationId: conversations.get(chat.id) ?? null });
        return injectPacket(prompt, cached.packet, settings.injectPosition, turn);
      }

      const t1 = host.now();
      const synced = await sync(settings, request, bodies, deadline);
      const syncMs = host.now() - t1;
      if (synced.conversation_id) {
        conversations.delete(chat.id);
        conversations.set(chat.id, synced.conversation_id);
        while (conversations.size > CACHE_LIMIT) conversations.delete(conversations.keys().next().value as string);
      }

      const { query, previousAi } = queryTexts(messages);
      const t2 = host.now();
      const retrieved = await call<{ freshness: string; packet: { text: string }; memory?: MemoryFit | null;
        vectors?: Vectors | null }>(settings, '/v1/retrieve', {
        host: 'pocketrisu',
        chat_id: chat.id,
        active_commit: synced.active_commit,
        manifest_hash: synced.manifest_hash,
        query,
        previous_ai: previousAi,
        in_context_ids: inContext,
        budget_tokens: settings.reservedMemoryTokens,
        client_timings_ms: { manifest: manifestMs, sync: syncMs, before_retrieve: t2 - started },
        canon_manifest_id: canon?.snapshot?.id ?? null,
        canon_held: canon?.held ?? [],
      }, deadline, undefined, late);
      if (canon?.snapshot && synced.conversation_id) syncCanon(settings, synced.conversation_id, chat.id, canon.snapshot);
      const packet = retrieved.freshness === 'fresh' ? retrieved.packet.text : '';
      const memory = retrieved.freshness === 'fresh' ? retrieved.memory ?? null : null; // older sidecars send none
      const vectors = retrieved.freshness === 'fresh' ? retrieved.vectors ?? null : null;
      // A delete, repair or settings save while this request ran: its packet may hold what that removed.
      if (epoch !== since) throw new Error('memory changed during this request');
      remember(key, packet, SUCCESS_TTL_MS, false, memory, vectors, canonKey);
      host.debug('[NMOS] request done', { ms: Math.round(host.now() - started), manifestMs: Math.round(manifestMs),
        syncMs: Math.round(syncMs), retrieveMs: Math.round(host.now() - t2), packetChars: packet.length });
      const outcome = packet ? 'injected' : 'nothing-relevant';
      last = { at: Date.now(), ms: Math.round(host.now() - started), packetChars: packet.length, packet, outcome,
        deadlineMs: settings.deadlineMs, budgetTokens: settings.reservedMemoryTokens, memory, vectors };
      emit({ type: 'request-end', outcome, chars: packet.length, vectors, conversationId: synced.conversation_id ?? null });
      return injectPacket(prompt, packet, settings.injectPosition, turn);
    } catch (error) {
      // Cache the miss briefly so host retries of this request (H2) do not wait out the deadline again.
      if (key && epoch === since) remember(key, '', FAILURE_TTL_MS, true);
      last = failure = { at: Date.now(), ms: Math.round(host.now() - started), packetChars: 0, packet: '', outcome: 'failed',
        error: error instanceof Error ? error.message : String(error), deadlineMs: settings?.deadlineMs ?? 0 };
      if (lateAt !== null) failure.neededMs = Math.round(lateAt - started);
      if (announced) emit({ type: 'request-end', outcome: 'failed', chars: 0, error: last.error,
        deadlineMs: last.deadlineMs, conversationId: (chatId && conversations.get(chatId)) || null });
      host.warn('[NMOS] memory skipped for this request (fail open):', error instanceof Error ? error.message : error);
      return prompt;
    }
  }

  /** Output listener: provisional hint only (H7). Never awaited work, never throws. */
  function onOutput(arg: { chat?: HostChat; messageIndex?: number }): void {
    void (async () => {
      const settings = await host.settings();
      if (!settings.enabled || !settings.sidecarUrl || !arg?.chat?.id || settings.offChats?.includes(arg.chat.id)) return;
      adviseOnce(settings.language);
      emit({ type: 'background', conversationId: conversations.get(arg.chat.id) ?? null });
      const index = arg.messageIndex ?? -1;
      const message = index >= 0 ? arg.chat.message?.[index] : undefined;
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

  /** Human-readable status for the settings menu (Korean first, English second). */
  async function status(): Promise<StatusInfo> {
    const settings = await host.settings();
    const info: StatusInfo = { enabled: settings.enabled, sidecarUrl: settings.sidecarUrl, language: settings.language,
      connected: false, last };
    try {
      const res = await call<{ version: string; features: Record<string, boolean>; plugin?: { expected: string | null } }>(
        settings, '/v1/health', undefined, host.now() + 3000);
      Object.assign(info, { connected: true, version: res.version, features: res.features ?? {},
        pluginExpected: res.plugin?.expected ?? null });
    } catch (error) {
      info.error = error instanceof Error ? error.message : String(error);
    }
    return info;
  }

  /** Sidecar API for the settings UI (longer timeout: connection tests call real models). */
  async function api<T>(method: 'GET' | 'POST' | 'PUT', path: string, body?: unknown, timeoutMs = 90_000): Promise<T> {
    const settings = await host.settings();
    // A settings save, rebuild or delete changes what a packet would contain: a reroll of an unchanged chat must not
    // reuse a packet built before it (a deleted chat's memory, old facts), nor one fetched while it ran. Also when the
    // answer failed or came after the timeout: the sidecar may have applied it, or apply it then.
    const change = method !== 'GET';
    if (change) invalidate();
    try {
      return await call<T>(settings, path, body, host.now() + timeoutMs, method, change ? invalidate : undefined);
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

  return { beforeRequest, onOutput, status, api, file, warmPersonas };
}

function firstSaying(messages: HostMessage[]): string | null {
  for (const m of messages) if (m.role === 'char' && m.saying) return m.saying;
  return null;
}
