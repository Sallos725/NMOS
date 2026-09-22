// The only module that touches the PocketRisu V3 `risuai` API. Read-only: never setChatToIndex.

import type { HostPort, Settings, StatusInfo } from './core';
import { langOf, t } from './i18n';
import type { InjectPosition } from './prompt';
import type { HostChat } from './types';
import { openPanel, type PanelDeps, type Tab } from './ui';

declare const risuai: {
  getArgument(key: string): Promise<string | number | undefined>;
  getCurrentCharacterIndex(): Promise<number>;
  getCurrentChatIndex(): Promise<number>;
  getChatFromIndex(characterIndex: number, chatIndex: number): Promise<HostChat | null>;
  getCharacterFromIndex(index: number): Promise<{ name?: string; chats?: { id?: string }[] } | null>;
  nativeFetch(url: string, options: Record<string, unknown>): Promise<Response>;
  addRisuReplacer(name: 'beforeRequest', fn: (prompt: unknown, mode: unknown) => unknown): Promise<void>;
  addRisuChatListener(mode: 'output', fn: (arg: unknown) => unknown): Promise<void>;
  registerSetting(name: string, callback: () => unknown, icon?: string, iconType?: string, id?: string): Promise<unknown>;
  registerButton(arg: { name: string; icon: string; iconType: 'html' | 'img' | 'none'; location?: 'action' | 'chat' | 'hamburger';
    id?: string }, callback: () => unknown): Promise<unknown>;
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
      language: langOf(await arg('language')),
    };
  },

  async currentChat(): Promise<HostChat | null> {
    const characterIndex = await risuai.getCurrentCharacterIndex();
    const chatIndex = await risuai.getCurrentChatIndex();
    return risuai.getChatFromIndex(characterIndex, chatIndex);
  },

  async characterName(chatId: string): Promise<string | null> {
    // The host returns a snapshot of the whole character (every chat), so this runs off the request path.
    const character = await risuai.getCharacterFromIndex(await risuai.getCurrentCharacterIndex());
    if (!character?.chats?.some((c) => c?.id === chatId)) return null; // switched characters meanwhile
    return typeof character.name === 'string' && character.name.trim() ? character.name.trim() : null;
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
  status: () => Promise<StatusInfo>,
  api: PanelDeps['api'],
): Promise<void> {
  await risuai.addRisuReplacer('beforeRequest', beforeRequest);
  await risuai.addRisuChatListener('output', onOutput);
  const deps: PanelDeps = {
    api,
    status,
    getArg: arg,
    setArg: (key, value) => risuai.setArgument(key, value),
    show: () => risuai.showContainer('fullscreen'),
    hide: () => risuai.hideContainer(),
  };
  const open = (tab: Tab) => openPanel(deps, tab);
  // Menu names are fixed at load, in the language chosen then (they follow a change after a reload).
  const lang = langOf(await arg('language'));
  await risuai.registerSetting(t(lang, 'menu.settings'), () => open('settings'), '⚙️', 'html', 'nmos-settings');
  await risuai.registerSetting(t(lang, 'menu.status'), () => open('status'), '🧠', 'html', 'nmos-status');
  // The ☰ menu left of the chat input.
  await risuai.registerButton({ name: t(lang, 'menu.panel'), icon: '🧠', iconType: 'html', location: 'chat', id: 'nmos-chat' },
    () => open('status'));
}
