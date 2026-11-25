// Settings form model: which sections changed, and the single sidecar update they add up to.

import { bodyKey, bodyOf } from './extrabody';

export type Section = 'conn' | 'llm' | 'emb' | 'rerank' | 'tune' | 'trim';

/** Request-path deadline when the plugin arg is unset (0). 3 s: on PocketRisu v1.12.0 a warm
 *  generation needs ≈1.5 s at 5,000 messages and ≈2.7 s at 10,000 (docs/perf/scale.md). */
export const DEFAULT_DEADLINE_MS = 3000;
export const MAX_DEADLINE_MS = 30_000;
/** Memory tokens reserved when the plugin arg is unset (0); the user lowers the host's max context by it (D2).
 *  800 since Phase 10 step 5 (was 600): Korean packets with a Private section pushed facts out at 600.
 *  2000 since Phase 12 step 5 (owner): the story so far did not fit 30 % of 800, and presets keep ~50,000 tokens of
 *  context. 4000 since Phase 15 (owner, ADR 0049): packet-v9's recall grows with the budget, and at 4,000 it answered
 *  more of the owner's cases than at 2,000; fixed, not the host's context. */
export const DEFAULT_RESERVED_TOKENS = 4000;
/** The largest memory budget the sidecar accepts (`RetrieveRequest.budget_tokens`); above it every request fails.
 *  A stored budget up to it is still read as it is. */
export const MAX_RESERVED_TOKENS = 20_000;
/** The largest budget the panel saves (ADR 0049): recall grows up to it, and a larger one recalls as it does. */
export const PANEL_MAX_RESERVED_TOKENS = 8000;
/** Old-dialogue trimming (PHASE-60 S1, ADR 0083): recent turns always sent, and the step the cut moves by.
 *  16 when the plugin arg is unset (0), a multiple of the sidecar's 8-turn window; kept within 4..200. */
export const DEFAULT_KEEP_RECENT_TURNS = 16;
export const MIN_KEEP_RECENT_TURNS = 4;
export const MAX_KEEP_RECENT_TURNS = 200;
/** Optional reranker wait (PHASE-60 S5, ADR 0084): 600 ms default, accepted within 50..5000 ms by the sidecar. */
export const DEFAULT_RERANK_TIMEOUT_MS = 600;
export const MIN_RERANK_TIMEOUT_MS = 50;
export const MAX_RERANK_TIMEOUT_MS = 5000;
/** `trim` is plugin args only, apart from `conn`: a connection save resets what the sidecar can do, and it has no
 *  part in the sidecar update `configBody` builds. */
export const SECTIONS: Section[] = ['conn', 'llm', 'emb', 'rerank', 'tune', 'trim'];

/** Google Vertex AI's OpenAI-compatible endpoint; `{project}` comes from the pasted key (ADR 0022). */
export const VERTEX_URL = 'https://aiplatform.googleapis.com/v1/projects/{project}/locations/global/endpoints/openapi';

/** The project of a pasted Google service-account JSON key, or null for anything else. */
export function serviceAccountProject(key: string): string | null {
  const text = key.trim();
  if (!text.startsWith('{')) return null;
  try {
    const info = JSON.parse(text) as { type?: unknown; project_id?: unknown };
    return info.type === 'service_account' && typeof info.project_id === 'string' && info.project_id
      ? info.project_id : null;
  } catch { return null; }
}

/** The endpoint with `{project}` filled from a pasted service-account key; unchanged otherwise. */
export function fillProject(url: string, key: string): string {
  const project = serviceAccountProject(key);
  return project && url.includes('{project}') ? url.replace('{project}', encodeURIComponent(project)) : url;
}

/** A Google Vertex AI endpoint, global or regional, with or without its project filled. */
export function isVertexEndpoint(url: string): boolean {
  return /^https:\/\/(?:[a-z0-9-]+-)?aiplatform\.googleapis\.com\//.test(url.trim());
}

/** A whole Vertex OpenAI-compatible endpoint, the shape the sidecar lists models for (`vertex.catalog_target`). */
const VERTEX_OPENAPI = /^https:\/\/(?:[a-z0-9-]+-)?aiplatform\.googleapis\.com\/v1(?:beta1)?\/projects\/[^/]+\/locations\/[^/]+\/endpoints\/openapi\/?$/;

/** The endpoint once a service-account key file is read: the Vertex preset with the key's project, unless it is
 *  already a whole custom (regional) Vertex endpoint with its project set, which stays as it is. */
export function endpointForKey(url: string, key: string): string {
  const u = url.trim();
  return VERTEX_OPENAPI.test(u) && !u.includes('{project}') && !presetMatches(VERTEX_URL, u) ? u : fillProject(VERTEX_URL, key);
}

/** A preset URL matches a saved one exactly, or with any project in place of `{project}`. */
/** The panel's Ollama preset: Docker reaches the PC's Ollama by host.docker.internal, a bundle (the sidecar says
 * `install: bundle`) at 127.0.0.1, where that name does not resolve (pre-0.4.0 audit F18). */
export const OLLAMA_DOCKER = 'http://host.docker.internal:11434/v1';
export const OLLAMA_LOCAL = 'http://127.0.0.1:11434/v1';
export function presetUrl(url: string, install: string | null | undefined): string {
  return url === OLLAMA_DOCKER && install === 'bundle' ? OLLAMA_LOCAL : url;
}

export function presetMatches(presetUrl: string, url: string): boolean {
  if (presetUrl === OLLAMA_DOCKER && url === OLLAMA_LOCAL) return true;
  if (!presetUrl.includes('{project}')) return presetUrl === url;
  const [head, tail] = presetUrl.split('{project}') as [string, string];
  return url.startsWith(head) && url.endsWith(tail) && url.length > head.length + tail.length
    && !url.slice(head.length, url.length - tail.length).includes('/');
}

export interface ModelValues { url: string; model: string; key: string }

export interface FormValues {
  conn: { url: string; route: string; enabled: boolean; reserved: string; deadline: string; token: string };
  /** `extra` (the JSON text) and `noTemp` only when the sidecar reports them (PHASE-61 S4, ADR 0088). */
  llm: ModelValues & { extra?: string; noTemp?: boolean };
  emb: ModelValues;
  /** Optional reranker (PHASE-60 S5, ADR 0084); sent only when the sidecar reported it. */
  rerank: { url: string; model: string; key: string; timeout: string };
  tune: { threshold: string; minSim: string; embedWait: string; topK: string; facts: string; backfill: string;
    summaries: boolean; canonFacts: boolean;
    /** Pin a character with @name in a message (PHASE-60 S8, ADR 0087); sent only when the sidecar has the setting. */
    pinAt: boolean;
    /** Chunks embedded per message (ADR 0062, `embed_max_chunks`), as typed; sent only when the sidecar reports it. */
    embedChunks?: string };
  /** Leaving out old dialogue (PHASE-60 S1): the switch and the recent turns always sent, as typed. */
  trim: { on: boolean; keep: string };
}

/** Sections whose values differ from the last loaded or saved baseline. */
export function dirtySections(baseline: FormValues, current: FormValues): Section[] {
  // the extra body counts by its object, not its spacing or key order
  const view = (v: FormValues, s: Section) => s === 'llm' && v.llm.extra !== undefined
    ? { ...v.llm, extra: bodyKey(v.llm.extra) } : v[s];
  return SECTIONS.filter((s) => JSON.stringify(view(baseline, s)) !== JSON.stringify(view(current, s)));
}

/** A save that changes what the extraction model is asked with: its address, its model, the extra body or the
 *  temperature switch (PHASE-61 S2: a body or switch change alone is a model change). */
export function modelChange(baseline: FormValues, current: FormValues): boolean {
  const [b, c] = [baseline.llm, current.llm];
  return c.url.trim() !== b.url.trim() || c.model.trim() !== b.model.trim()
    || bodyKey(c.extra ?? '') !== bodyKey(b.extra ?? '') || Boolean(c.noTemp) !== Boolean(b.noTemp);
}

/** A number field as the sidecar expects it; anything unparsable is sent as typed so the sidecar
 *  rejects it with a message instead of it silently becoming 0 or a reset. */
function num(value: string): number | string {
  const n = Number(value.trim());
  return value.trim() !== '' && Number.isFinite(n) ? n : value;
}

/** Settings a sidecar reports only from the version that has them; one it did not report is never sent. */
export interface KnownSettings { pinAt?: boolean; rerank?: boolean; embedChunks?: boolean }

/** Chunks embedded per message (ADR 0062): the sidecar's default, the panel's range, and the characters one covers
 *  (`vectors.CHUNK_CHARS`). A changed cap is a new projection: the chats are embedded again. */
export const DEFAULT_EMBED_MAX_CHUNKS = 8;
export const MIN_EMBED_MAX_CHUNKS = 1;
export const MAX_EMBED_MAX_CHUNKS = 64;
export const EMBED_CHUNK_CHARS = 700;

/** The characters of a message `chunks` covers, or null when it is not a whole number in the panel's range. */
export function embedChunkChars(chunks: string): number | null {
  const n = Number(chunks.trim());
  return chunks.trim() !== '' && Number.isInteger(n) && n >= MIN_EMBED_MAX_CHUNKS && n <= MAX_EMBED_MAX_CHUNKS
    ? n * EMBED_CHUNK_CHARS : null;
}

/** One PUT /v1/config body for every changed server-side section (validated and saved atomically). With `base`, the
 *  extra body and the temperature switch are sent when they differ from it (PHASE-61 S4). */
export function configBody(dirty: Section[], v: FormValues, known: KnownSettings = {}, base?: FormValues): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  for (const [section, prefix] of [['llm', 'llm'], ['emb', 'embed']] as const) {
    if (!dirty.includes(section)) continue;
    body[`${prefix}_url`] = v[section].url.trim();
    body[`${prefix}_model`] = v[section].model.trim();
    if (v[section].key.trim()) body[`${prefix}_api_key`] = v[section].key.trim();
  }
  if (dirty.includes('llm') && base) {
    const extra = v.llm.extra === undefined ? null : bodyOf(v.llm.extra);  // null: an older sidecar, or not an object
    if (extra && bodyKey(v.llm.extra as string) !== bodyKey(base.llm.extra ?? '')) body.llm_extra_body = extra;
    if (v.llm.noTemp !== undefined && v.llm.noTemp !== Boolean(base.llm.noTemp)) body.llm_no_temperature = v.llm.noTemp;
  }
  if (dirty.includes('rerank') && known.rerank) {
    body.rerank_url = v.rerank.url.trim();
    body.rerank_model = v.rerank.model.trim();
    body.rerank_timeout_ms = num(v.rerank.timeout);
    if (v.rerank.key.trim()) body.rerank_api_key = v.rerank.key.trim();
  }
  if (dirty.includes('tune')) {
    Object.assign(body, {
      recall_threshold: num(v.tune.threshold), vector_min_sim: num(v.tune.minSim), recall_top_k: num(v.tune.topK),
      facts_limit: num(v.tune.facts), extract_backfill: num(v.tune.backfill), summaries: v.tune.summaries,
      canon_facts: v.tune.canonFacts,
    });
    // empty when the sidecar is older than the setting: sending it would be refused as not editable
    if (v.tune.embedWait.trim() !== '') body.embed_timeout_ms = num(v.tune.embedWait);
    if (known.pinAt) body.pin_at_mentions = v.tune.pinAt;  // likewise: an older sidecar has no such setting
    // likewise, and only when it changed: a changed cap embeds every chat again (ADR 0062)
    const chunks = v.tune.embedChunks?.trim() ?? '';
    if (known.embedChunks && chunks !== '' && chunks !== (base?.tune.embedChunks?.trim() ?? '')) {
      body.embed_max_chunks = num(chunks);
    }
  }
  return body;
}

/** Room the rest of a request needs besides the embedding wait (the sync, the reads, the packet). */
export const EMBED_WAIT_MARGIN_MS = 500;

/** Whether the embedding wait leaves the request too little of its deadline (pre-0.4.0 audit F20): a slow embedder
 * then costs the whole memory, not only semantic search. The wait is a sidecar setting and the deadline a per-device
 * plugin argument, so this warns and does not refuse. */
export function embedWaitTooLong(wait: string, deadline: string): boolean {
  const w = Number(wait.trim());
  const d = Number(deadline.trim()) || DEFAULT_DEADLINE_MS;
  return wait.trim() !== '' && Number.isFinite(w) && w > d - EMBED_WAIT_MARGIN_MS;
}

/** Plugin args for the connection section (stored in PocketRisu, not the sidecar). */
export function connArgs(v: FormValues['conn']): Record<string, string | number> {
  return {
    sidecar_url: v.url.trim(),
    route: v.route,
    disabled: v.enabled ? 0 : 1,
    reserved_memory_tokens: Math.min(PANEL_MAX_RESERVED_TOKENS, Math.floor(Number(v.reserved)) > 0
      ? Math.floor(Number(v.reserved)) : DEFAULT_RESERVED_TOKENS),
    deadline_ms: Math.min(MAX_DEADLINE_MS, Math.max(200, Math.floor(Number(v.deadline)) || DEFAULT_DEADLINE_MS)),
    auth_token: v.token.trim(),
  };
}

/** Plugin args for leaving out old dialogue (PHASE-60 S1, ADR 0083; stored in PocketRisu, not the sidecar): the switch
 *  as 1 or 0, and the recent turns always sent, a whole number within 4..200 that is 16 when empty or not positive.
 *  `host.ts` reads every value this returns back as it is. */
export function trimArgs(v: { on: boolean; keep: string }): { trim_old_turns: 0 | 1; keep_recent_turns: number } {
  const n = Math.floor(Number(v.keep.trim()));
  const keep = Number.isFinite(n) && n > 0 ? n : DEFAULT_KEEP_RECENT_TURNS;
  return {
    trim_old_turns: v.on ? 1 : 0,
    keep_recent_turns: Math.min(MAX_KEEP_RECENT_TURNS, Math.max(MIN_KEEP_RECENT_TURNS, keep)),
  };
}
