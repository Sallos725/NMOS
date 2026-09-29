// The only module that touches the PocketRisu V3 `risuai` API. Read-only: never setChatToIndex.

import type { HostPort, Settings, StatusInfo } from './core';
import { langOf, t } from './i18n';
import type { InjectPosition } from './prompt';
import type { HostCard, HostLoreEntry } from './canon';
import { CHAT_OFF_ARG, createChatSwitch, parseChatIds, type ChatState } from './chatoff';
import type { HostChat, HostPersonas } from './types';
import { DEFAULT_DEADLINE_MS, DEFAULT_RESERVED_TOKENS, MAX_DEADLINE_MS, MAX_RESERVED_TOKENS } from './form';
import { createHud, type HudDocument } from './hud-host';
import { NMOS_ICON, namedIcon } from './icon';
import { routeFor } from './route';
import { openPanel, type HudControl, type PanelDeps, type Tab } from './ui';

export { routeFor };

declare const risuai: {
  getArgument(key: string): Promise<string | number | undefined>;
  getCurrentCharacterIndex(): Promise<number>;
  getCurrentChatIndex(): Promise<number>;
  getChatFromIndex(characterIndex: number, chatIndex: number): Promise<HostChat | null>;
  getCharacterFromIndex(index: number): Promise<(HostCard & { chats?: { id?: string }[] }) | null>;
  getCurrentLorebookEntries?(): Promise<HostLoreEntry[]>;
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

async function arg(key: string): Promise<string> {
  return String((await risuai.getArgument(key)) ?? '').trim();
}

function fetchOptions(route: 'direct' | 'server'): Record<string, unknown> {
  return route === 'server' ? { networkRoute: 'local_network' } : {};
}

// PocketRisu initialises int args to 0, so 0 means "use the default". The host's own argument field has no
// upper limit, unlike the panel, so a value past it is capped here.
function positiveInt(value: string, fallback: number, max: number): number {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? Math.min(max, Math.floor(n)) : fallback;
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
      reservedMemoryTokens: positiveInt(await arg('reserved_memory_tokens'), DEFAULT_RESERVED_TOKENS, MAX_RESERVED_TOKENS),
      deadlineMs: positiveInt(await arg('deadline_ms'), DEFAULT_DEADLINE_MS, MAX_DEADLINE_MS),
      injectPosition: (position === 'end' ? 'end' : 'before_last_user') as InjectPosition,
      language: langOf(await arg('language')),
      offChats: parseChatIds(await arg(CHAT_OFF_ARG)),
    };
  },

  async currentChat(): Promise<HostChat | null> {
    const characterIndex = await risuai.getCurrentCharacterIndex();
    const chatIndex = await risuai.getCurrentChatIndex();
    return risuai.getChatFromIndex(characterIndex, chatIndex);
  },

  async characterName(chatId: string): Promise<string | null> {
    const card = await this.card!(chatId);
    return typeof card?.name === 'string' && card.name.trim() ? card.name.trim() : null;
  },

  async card(chatId: string): Promise<HostCard | null> {
    // The host clones the current chat with the character (H19: 82-93 ms at 10,000 messages), so this runs off the
    // request path. Only the story fields are kept (PHASE-14 Q1).
    const character = await risuai.getCharacterFromIndex(await risuai.getCurrentCharacterIndex());
    if (!character?.chats?.some((c) => c?.id === chatId)) return null; // switched characters meanwhile
    const { name, desc, personality, scenario, firstMessage, alternateGreetings, globalLore } = character;
    return { name, desc, personality, scenario, firstMessage, alternateGreetings, globalLore };
  },

  async lorebook(): Promise<HostLoreEntry[]> {
    // Every entry of the character, the chat and the enabled modules, activated or not; about 1 ms (H19).
    // No lorebook call, or no list, is no observation: an empty list would end every entry (ADR 0045).
    if (typeof risuai.getCurrentLorebookEntries !== 'function') throw new Error('no lorebook call on this host');
    const entries = await risuai.getCurrentLorebookEntries();
    if (!Array.isArray(entries)) throw new Error('the host returned no lorebook list');
    return entries;
  },

  async personas(): Promise<HostPersonas | null> {
    if (typeof risuai.getDatabase !== 'function') return null;
    const db = await risuai.getDatabase(['personas', 'selectedPersona']);
    if (!db || !Array.isArray(db.personas)) return null;
    const personas = db.personas.map((p) => {
      const { id, name, personaPrompt } = (p ?? {}) as { id?: unknown; name?: unknown; personaPrompt?: unknown };
      return { id: typeof id === 'string' ? id : undefined, name: typeof name === 'string' ? name : undefined,
        personaPrompt: typeof personaPrompt === 'string' ? personaPrompt : undefined };
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

  async requestFile(url, headers, timeoutMs, route) {
    const res = await risuai.nativeFetch(url, {
      method: 'GET',
      headers,
      requestTimeoutMs: Math.max(1, Math.floor(timeoutMs)),
      ...fetchOptions(route),
    });
    // Binary bodies arrive whole through nativeFetch on both routes (H21).
    const bytes = await res.arrayBuffer();
    if (res.status >= 200 && res.status < 300) return { status: res.status, bytes, json: null };
    let json: unknown = null;
    try {
      json = JSON.parse(new TextDecoder().decode(bytes));
    } catch {
      json = null;
    }
    return { status: res.status, bytes: null, json };
  },

  warn: (...args) => console.warn(...args),
  debug: (...args) => console.debug(...args),
  now: () => performance.now(),
  // PocketRisu's alertNormal: one global dialog, so core.ts calls it only after a reply (audit A-09).
  alert: (message) => { risuai.alert(message).catch(() => {}); },
};

/** The progress display (D28) on the PocketRisu page, and its toggle for the panel. */
export function createRisuHud(link: { coverage(conversationId: string): Promise<unknown>; openPanel(): void }) {
  const hud = createHud({
    enabled: async () => Number(await arg('hud')) === 1,
    lang: async () => langOf(await arg('language')),
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

/** Switching NMOS off and on for the chat open now (ADR 0048). */
export const risuChatSwitch = createChatSwitch({
  getArg: arg,
  setArg: (key, value) => risuai.setArgument(key, value),
  async currentChatId() {
    const characterIndex = await risuai.getCurrentCharacterIndex();
    if (characterIndex < 0) return null;
    const chat = await risuai.getChatFromIndex(characterIndex, await risuai.getCurrentChatIndex());
    return typeof chat?.id === 'string' && chat.id ? chat.id : null;
  },
});

/** What a tap on the chat menu's switch did, for the host's dialog. The global switch wins (ADR 0048 §5). */
export function chatSwitchNotice(lang: Parameters<typeof t>[0], state: ChatState, enabled: boolean): string {
  if (state.id === null) return t(lang, 'chat.none');
  if (state.off) return t(lang, 'chat.switched_off');
  return t(lang, enabled ? 'chat.switched_on' : 'chat.switched_on_all_off');
}

/** Save bytes as a file through the browser (H21): a Blob on a link with `download`, clicked by script. A link to the
 * sidecar would navigate the plugin frame instead. */
export function saveFile(bytes: ArrayBuffer, name: string, type = 'application/zip'): void {
  const url = URL.createObjectURL(new Blob([bytes], { type }));
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.style.display = 'none';
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

export async function registerHooks(
  beforeRequest: (prompt: unknown, mode: unknown) => Promise<unknown>,
  onOutput: (arg: unknown) => void,
  status: () => Promise<StatusInfo>,
  api: PanelDeps['api'],
  file: (path: string) => Promise<ArrayBuffer>,
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
    chat: risuChatSwitch,
    async download(path, name) {
      const bytes = await file(path);
      saveFile(bytes, name);
      return bytes.byteLength;
    },
  };
  const open = (tab: Tab) => openPanel(deps, tab);
  // Menu names are fixed at load, in the language chosen then (they follow a change after a reload).
  const lang = langOf(await arg('language'));
  // One entry in PocketRisu settings: the panel has status, inspector and settings tabs.
  await risuai.registerSetting(t(lang, 'menu.panel'), () => open('status'), NMOS_ICON, 'html', 'nmos-panel');
  // The ☰ menu left of the chat input.
  await risuai.registerButton({ name: t(lang, 'menu.panel'), icon: NMOS_ICON, iconType: 'html', location: 'chat', id: 'nmos-chat' },
    () => open('status'));
  // The same menu: switch NMOS off or back on for this chat in one tap (ADR 0048). Its name is fixed at load, so the
  // host's dialog says which way it went.
  await risuai.registerButton({ name: t(lang, 'menu.chat_switch'), icon: '⏻', iconType: 'html', location: 'chat',
    id: 'nmos-chat-switch' }, () => {
    risuChatSwitch.toggle()
      .then(async (state) => risuai.alert(chatSwitchNotice(lang, state, Number(await arg('disabled')) !== 1)))
      .catch((error) => console.warn('[NMOS] chat switch failed:', error instanceof Error ? error.message : error));
  });
  // The sidebar's ☰ menu, which shows icons only (PocketRisu v1.13.0 Sidebar.svelte): the panel, where "This chat"
  // is the first card.
  await risuai.registerButton({ name: t(lang, 'menu.panel'), icon: namedIcon(t(lang, 'menu.panel')), iconType: 'html',
    location: 'hamburger', id: 'nmos-sidebar' }, () => open('status'));
  return () => void open('status');
}
