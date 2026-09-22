// Request-path orchestration. Host access comes in through `HostPort`; everything fails open.

import { canonicalJson } from './canonical';
import { sha256Hex } from './hash';
import { bodyKey, buildManifest, hashPayload } from './manifest';
import { hasPacket, inContextIds, injectPacket, isMainGeneration, queryTexts, type InjectPosition } from './prompt';
import type { Body, HostChat, HostMessage, PromptMessage, ReconcileRequest } from './types';

export interface Settings {
  sidecarUrl: string;
  authToken: string;
  enabled: boolean;
  reservedMemoryTokens: number;
  deadlineMs: number;
  injectPosition: InjectPosition;
  /** 'direct' = browser fetch (proxy fallback); 'server' = always via the PocketRisu server. */
  route: 'direct' | 'server';
}

export interface HttpResult {
  status: number;
  json: unknown;
}

export interface HostPort {
  settings(): Promise<Settings>;
  currentChat(): Promise<HostChat | null>;
  request(method: 'GET' | 'POST' | 'PUT', url: string, body: unknown, headers: Record<string, string>,
          timeoutMs: number, route: Settings['route']): Promise<HttpResult>;
  warn(...args: unknown[]): void;
  debug(...args: unknown[]): void;
  now(): number;
}

class DeadlineError extends Error {}

interface ReconcileResult {
  status: 'noop' | 'applied' | 'needs_bodies';
  active_commit: string | null;
  manifest_hash: string;
  needed_bodies?: { host_logical_id: string; revision_hash: string }[];
}

interface CacheEntry {
  packet: string;
  expires: number;
}

const SUCCESS_TTL_MS = 10 * 60_000;
const FAILURE_TTL_MS = 30_000;
const CACHE_LIMIT = 64;
const BODY_CHUNK = 250;

export interface LastRequest {
  at: number;
  ms: number;
  packetChars: number;
  outcome: 'injected' | 'nothing-relevant' | 'failed';
  error?: string;
}

export function createAdapter(host: HostPort) {
  const cache = new Map<string, CacheEntry>();
  let last: LastRequest | null = null;

  function remember(key: string, packet: string, ttl: number): void {
    cache.set(key, { packet, expires: host.now() + ttl });
    while (cache.size > CACHE_LIMIT) cache.delete(cache.keys().next().value as string);
  }

  async function call<T>(settings: Settings, path: string, body: unknown, deadline: number,
                         method?: 'GET' | 'POST' | 'PUT'): Promise<T> {
    const remaining = deadline - host.now();
    if (remaining <= 0) throw new DeadlineError(`deadline before ${path}`);
    const url = settings.sidecarUrl.replace(/\/+$/, '') + path;
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (settings.authToken) headers.Authorization = `Bearer ${settings.authToken}`;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const timeout = new Promise<never>((_, reject) => {
      timer = setTimeout(() => reject(new DeadlineError(`deadline during ${path}`)), remaining);
    });
    try {
      const verb = method ?? (body === undefined ? 'GET' : 'POST');
      const res = await Promise.race([host.request(verb, url, body, headers, remaining, settings.route), timeout]);
      if (res.status < 200 || res.status >= 300) {
        const detail = (res.json as { detail?: unknown } | null)?.detail;
        throw new Error(`${path} -> HTTP ${res.status}${detail ? `: ${Array.isArray(detail) ? detail.join('; ') : String(detail)}` : ''}`);
      }
      return res.json as T;
    } finally {
      clearTimeout(timer);
    }
  }

  async function sync(settings: Settings, request: ReconcileRequest, bodies: Map<string, Body>, deadline: number) {
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
    let settings: Settings | null = null;
    let key: string | null = null;
    try {
      if (mode !== 'model' || hasPacket(prompt)) return prompt; // aux request, or retry of an injected prompt (H2)
      settings = await host.settings();
      if (!settings.enabled || !settings.sidecarUrl) return prompt;
      const deadline = started + settings.deadlineMs;

      const chat = await host.currentChat();
      const messages: HostMessage[] = Array.isArray(chat?.message) ? chat!.message : [];
      if (!chat?.id || !isMainGeneration(prompt, mode, messages)) return prompt;

      // Cache key = exact chat state (every message id + revision hash) + prompt shape, so a cached
      // packet is reused only for the same state (host retries, reroll of an unchanged chat) and never
      // survives an edit anywhere in the chat.
      const t0 = host.now();
      const { request, bodies } = await buildManifest(chat, firstSaying(messages));
      const manifestMs = host.now() - t0;
      key = await sha256Hex(canonicalJson([
        chat.id, mode, prompt.length, request.messages.map((m) => [m.host_logical_id, m.revision_hash]),
      ]));
      const cached = cache.get(key);
      if (cached && cached.expires > host.now()) return injectPacket(prompt, cached.packet, settings.injectPosition);

      const t1 = host.now();
      const synced = await sync(settings, request, bodies, deadline);
      const syncMs = host.now() - t1;

      const { query, previousAi } = queryTexts(messages);
      const t2 = host.now();
      const retrieved = await call<{ freshness: string; packet: { text: string } }>(settings, '/v1/retrieve', {
        host: 'pocketrisu',
        chat_id: chat.id,
        active_commit: synced.active_commit,
        manifest_hash: synced.manifest_hash,
        query,
        previous_ai: previousAi,
        in_context_ids: inContextIds(prompt, messages),
        budget_tokens: settings.reservedMemoryTokens,
        client_timings_ms: { manifest: manifestMs, sync: syncMs, before_retrieve: t2 - started },
      }, deadline);
      const packet = retrieved.freshness === 'fresh' ? retrieved.packet.text : '';
      remember(key, packet, SUCCESS_TTL_MS);
      host.debug('[NMOS] request done', { ms: Math.round(host.now() - started), manifestMs: Math.round(manifestMs),
        syncMs: Math.round(syncMs), retrieveMs: Math.round(host.now() - t2), packetChars: packet.length });
      last = { at: Date.now(), ms: Math.round(host.now() - started), packetChars: packet.length,
        outcome: packet ? 'injected' : 'nothing-relevant' };
      return injectPacket(prompt, packet, settings.injectPosition);
    } catch (error) {
      // Cache the miss briefly so host retries of this request (H2) do not wait out the deadline again.
      if (key) remember(key, '', FAILURE_TTL_MS);
      last = { at: Date.now(), ms: Math.round(host.now() - started), packetChars: 0, outcome: 'failed',
        error: error instanceof Error ? error.message : String(error) };
      host.warn('[NMOS] memory skipped for this request (fail open):', error instanceof Error ? error.message : error);
      return prompt;
    }
  }

  /** Output listener: provisional hint only (H7). Never awaited work, never throws. */
  function onOutput(arg: { chat?: HostChat; messageIndex?: number }): void {
    void (async () => {
      const settings = await host.settings();
      if (!settings.enabled || !settings.sidecarUrl || !arg?.chat?.id) return;
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

  /** Human-readable status for the settings menu (Korean first, English second). */
  async function statusText(): Promise<string> {
    const settings = await host.settings();
    const lines: string[] = [];
    if (!settings.enabled) lines.push('NMOS: 꺼짐 (disabled = 1) / disabled');
    try {
      const res = await call<{ version: string; features: Record<string, boolean> }>(
        settings, '/v1/health', undefined, host.now() + 3000);
      const f = res.features ?? {};
      const on = (b: boolean | undefined) => (b ? 'on' : 'off');
      lines.push(`NMOS ${res.version} 연결됨 / connected — ${settings.sidecarUrl}`);
      lines.push(`상태창 state ${on(f.state)} · 사실 facts ${on(f.extraction)} · 의미검색 vectors ${on(f.vectors)}`);
    } catch (error) {
      lines.push(`사이드카에 연결할 수 없음 / cannot reach sidecar: ${settings.sidecarUrl}`);
      lines.push(`(${error instanceof Error ? error.message : String(error)})`);
      lines.push('확인: docker compose up -d · NMOS_CORS_ORIGINS에 이 주소 포함 · localhost/HTTPS로 접속');
    }
    if (last) {
      const ago = Math.round((Date.now() - last.at) / 1000);
      const what = last.outcome === 'injected' ? `기억 주입 ${last.packetChars}자 / injected`
        : last.outcome === 'nothing-relevant' ? '관련 기억 없음 / nothing relevant' : `실패 / failed: ${last.error}`;
      lines.push(`마지막 요청 / last request: ${ago}s 전 · ${what} · ${last.ms}ms`);
    } else {
      lines.push('아직 요청 없음 — 메시지를 보내 보세요 / no request yet');
    }
    return lines.join('\n');
  }

  /** Sidecar API for the settings UI (longer timeout: connection tests call real models). */
  async function api<T>(method: 'GET' | 'POST' | 'PUT', path: string, body?: unknown, timeoutMs = 90_000): Promise<T> {
    const settings = await host.settings();
    return call<T>(settings, path, body, host.now() + timeoutMs, method);
  }

  return { beforeRequest, onOutput, statusText, api };
}

function firstSaying(messages: HostMessage[]): string | null {
  for (const m of messages) if (m.role === 'char' && m.saying) return m.saying;
  return null;
}
