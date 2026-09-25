// The only module that touches the PocketRisu V3 `risuai` API. Read-only: never setChatToIndex.

import type { HostPort, Settings, StatusInfo } from './core';
import { langOf, t } from './i18n';
import type { InjectPosition } from './prompt';
import type { HostChat, HostPersonas } from './types';
import { DEFAULT_DEADLINE_MS } from './form';
import { createHud, placementOf, type HudDocument } from './hud-host';
import { routeFor } from './route';
import { openPanel, type HudControl, type PanelDeps, type Tab } from './ui';

export { routeFor };

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
  // Lite database view (ADR 0023): asks the host's "db" permission once; null when refused.
  getDatabase?(includeOnly: string[]): Promise<{ personas?: unknown; selectedPersona?: unknown } | null>;
  // Main-page access (H16); missing on older builds.
  requestPluginPermission?(permission: 'mainDom'): Promise<boolean>;
  getRootDocument?(): Promise<HudDocument | null>;
};

const DEFAULT_SIDECAR_URL = 'http://127.0.0.1:8790';
const DEFAULT_RESERVED_TOKENS = 600;

async function arg(key: string): Promise<string> {
  return String((await risuai.getArgument(key)) ?? '').trim();
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

  async personas(): Promise<HostPersonas | null> {
    if (typeof risuai.getDatabase !== 'function') return null;
    const db = await risuai.getDatabase(['personas', 'selectedPersona']);
    if (!db || !Array.isArray(db.personas)) return null;
    const personas = db.personas.map((p) => {
      const { id, name } = (p ?? {}) as { id?: unknown; name?: unknown };
      return { id: typeof id === 'string' ? id : undefined, name: typeof name === 'string' ? name : undefined };
    });
    return { personas, selected: Number.isInteger(db.selectedPersona) ? Number(db.selectedPersona) : 0 };
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

/** The progress display (D28) on the PocketRisu page, and its toggle for the panel. */
export function createRisuHud(link: { coverage(conversationId: string): Promise<unknown>; openPanel(): void }) {
  const hud = createHud({
    enabled: async () => Number(await arg('hud')) === 1,
    lang: async () => langOf(await arg('language')),
    placement: async () => placementOf(await arg('hud_position')),
    rootDocument: async () => (typeof risuai.getRootDocument === 'function' ? risuai.getRootDocument() : null),
    position: async () => `${await risuai.getCurrentCharacterIndex()}:${await risuai.getCurrentChatIndex()}`,
    coverage: (conversationId) => link.coverage(conversationId),
    openPanel: () => link.openPanel(),
    now: () => performance.now(),
    debug: (...args) => console.debug(...args),
    setTimer: (fn, ms) => setTimeout(fn, ms),
    clearTimer: (handle) => clearTimeout(handle as ReturnType<typeof setTimeout>),
  });
  const control: HudControl & { event: typeof hud.event } = {
    event: hud.event,
    async enable() {
      if (typeof risuai.requestPluginPermission !== 'function' || typeof risuai.getRootDocument !== 'function') {
        return 'unsupported';
      }
      // The host's permission dialog would open under the full-screen panel frame (z-index 1000): hide
      // the frame while it asks.
      await risuai.hideContainer();
      let granted = false;
      try {
        granted = (await risuai.requestPluginPermission('mainDom')) === true;
      } finally {
        await risuai.showContainer('fullscreen');
      }
      await risuai.setArgument('hud', granted ? 1 : 0);
      hud.refresh();
      return granted ? 'on' : 'denied';
    },
    async disable() {
      await risuai.setArgument('hud', 0);
      hud.refresh();
    },
    problem: hud.problem,
    background: hud.background,
  };
  return control;
}

export async function registerHooks(
  beforeRequest: (prompt: unknown, mode: unknown) => Promise<unknown>,
  onOutput: (arg: unknown) => void,
  status: () => Promise<StatusInfo>,
  api: PanelDeps['api'],
  hud: HudControl,
): Promise<() => void> {
  await risuai.addRisuReplacer('beforeRequest', beforeRequest);
  await risuai.addRisuChatListener('output', onOutput);
  const deps: PanelDeps = {
    api,
    status,
    getArg: arg,
    setArg: (key, value) => risuai.setArgument(key, value),
    show: () => risuai.showContainer('fullscreen'),
    hide: () => risuai.hideContainer(),
    hud,
  };
  const open = (tab: Tab) => openPanel(deps, tab);
  // Menu names are fixed at load, in the language chosen then (they follow a change after a reload).
  const lang = langOf(await arg('language'));
  // One entry in PocketRisu settings: the panel has status, inspector and settings tabs.
  await risuai.registerSetting(t(lang, 'menu.panel'), () => open('status'), '🧠', 'html', 'nmos-panel');
  // The ☰ menu left of the chat input.
  await risuai.registerButton({ name: t(lang, 'menu.panel'), icon: '🧠', iconType: 'html', location: 'chat', id: 'nmos-chat' },
    () => open('status'));
  return () => void open('status');
}
