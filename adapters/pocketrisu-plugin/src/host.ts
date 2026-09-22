// The only module that touches the PocketRisu V3 `risuai` API. Read-only: never setChatToIndex.

import type { HostPort, Settings } from './core';
import type { InjectPosition } from './prompt';
import type { HostChat } from './types';
import { openSettingsPanel, type PanelDeps } from './ui';

declare const risuai: {
  getArgument(key: string): Promise<string | number | undefined>;
  getCurrentCharacterIndex(): Promise<number>;
  getCurrentChatIndex(): Promise<number>;
  getChatFromIndex(characterIndex: number, chatIndex: number): Promise<HostChat | null>;
  nativeFetch(url: string, options: Record<string, unknown>): Promise<Response>;
  addRisuReplacer(name: 'beforeRequest', fn: (prompt: unknown, mode: unknown) => unknown): Promise<void>;
  addRisuChatListener(mode: 'output', fn: (arg: unknown) => unknown): Promise<void>;
  registerSetting(name: string, callback: () => unknown, icon?: string, iconType?: string, id?: string): Promise<unknown>;
  alert(message: string): Promise<void>;
  setArgument(key: string, value: string | number): Promise<void>;
  showContainer(type: 'fullscreen'): Promise<void>;
  hideContainer(): Promise<void>;
};

const DEFAULT_SIDECAR_URL = 'http://127.0.0.1:8790';
const DEFAULT_RESERVED_TOKENS = 600;
const DEFAULT_DEADLINE_MS = 800;

async function arg(key: string): Promise<string> {
  return String((await risuai.getArgument(key)) ?? '').trim();
}

// A sidecar on this machine is reached directly from the browser. Anything else (LAN IP, Docker
// service name) goes through the PocketRisu server: an HTTPS page cannot fetch http:// directly, and
// a Docker name only resolves on the server. PocketRisu routes local-network hosts via /proxy2.
export function routeFor(url: string, setting: string): 'direct' | 'server' {
  if (setting === 'direct' || setting === 'server') return setting;
  try {
    const host = new URL(url).hostname.replace(/^\[|\]$/g, '');
    return ['localhost', '127.0.0.1', '::1'].includes(host) ? 'direct' : 'server';
  } catch {
    return 'direct';
  }
}

function fetchOptions(route: 'direct' | 'server'): Record<string, unknown> {
  return route === 'server' ? { networkRoute: 'local_network' } : {};
}

// PocketRisu initialises int args to 0, so 0 means "use the default".
function positiveInt(value: string, fallback: number): number {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : fallback;
}

export const risuHost: HostPort = {
  async settings(): Promise<Settings> {
    const position = await arg('inject_position');
    const sidecarUrl = (await arg('sidecar_url')) || DEFAULT_SIDECAR_URL;
    return {
      sidecarUrl,
      route: routeFor(sidecarUrl, await arg('route')),
      authToken: await arg('auth_token'),
      enabled: Number(await arg('disabled')) !== 1,
      reservedMemoryTokens: positiveInt(await arg('reserved_memory_tokens'), DEFAULT_RESERVED_TOKENS),
      deadlineMs: positiveInt(await arg('deadline_ms'), DEFAULT_DEADLINE_MS),
      injectPosition: (position === 'end' ? 'end' : 'before_last_user') as InjectPosition,
    };
  },

  async currentChat(): Promise<HostChat | null> {
    const characterIndex = await risuai.getCurrentCharacterIndex();
    const chatIndex = await risuai.getCurrentChatIndex();
    return risuai.getChatFromIndex(characterIndex, chatIndex);
  },

  async request(method, url, body, headers, timeoutMs, route) {
    const res = await risuai.nativeFetch(url, {
      method,
      headers,
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      requestTimeoutMs: Math.max(1, Math.floor(timeoutMs)),
      ...fetchOptions(route),
    });
    let json: unknown = null;
    try {
      json = await res.json();
    } catch {
      json = null;
    }
    return { status: res.status, json };
  },

  warn: (...args) => console.warn(...args),
  debug: (...args) => console.debug(...args),
  now: () => performance.now(),
};

export async function registerHooks(
  beforeRequest: (prompt: unknown, mode: unknown) => Promise<unknown>,
  onOutput: (arg: unknown) => void,
  status: () => Promise<string>,
  api: PanelDeps['api'],
): Promise<void> {
  await risuai.addRisuReplacer('beforeRequest', beforeRequest);
  await risuai.addRisuChatListener('output', onOutput);
  await risuai.registerSetting('NMOS 설정 / Settings', async () => {
    await openSettingsPanel({
      api,
      getArg: arg,
      setArg: (key, value) => risuai.setArgument(key, value),
      show: () => risuai.showContainer('fullscreen'),
      hide: () => risuai.hideContainer(),
    });
  }, '⚙️', 'html', 'nmos-settings');
  await risuai.registerSetting('NMOS 상태 / Status', async () => {
    await risuai.alert(await status());
  }, '🧠', 'html', 'nmos-status');
}
