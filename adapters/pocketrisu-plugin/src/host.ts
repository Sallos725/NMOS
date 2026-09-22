// The only module that touches the PocketRisu V3 `risuai` API. Read-only: never setChatToIndex.

import type { HostPort, Settings } from './core';
import type { InjectPosition } from './prompt';
import type { HostChat } from './types';

declare const risuai: {
  getArgument(key: string): Promise<string | number | undefined>;
  getCurrentCharacterIndex(): Promise<number>;
  getCurrentChatIndex(): Promise<number>;
  getChatFromIndex(characterIndex: number, chatIndex: number): Promise<HostChat | null>;
  nativeFetch(url: string, options: Record<string, unknown>): Promise<Response>;
  addRisuReplacer(name: 'beforeRequest', fn: (prompt: unknown, mode: unknown) => unknown): Promise<void>;
  addRisuChatListener(mode: 'output', fn: (arg: unknown) => unknown): Promise<void>;
};

const DEFAULT_RESERVED_TOKENS = 600;
const DEFAULT_DEADLINE_MS = 800;

async function arg(key: string): Promise<string> {
  return String((await risuai.getArgument(key)) ?? '').trim();
}

// PocketRisu initialises int args to 0, so 0 means "use the default".
function positiveInt(value: string, fallback: number): number {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : fallback;
}

export const risuHost: HostPort = {
  async settings(): Promise<Settings> {
    const position = await arg('inject_position');
    return {
      sidecarUrl: await arg('sidecar_url'),
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

  async post(url, body, headers, timeoutMs) {
    const res = await risuai.nativeFetch(url, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
      requestTimeoutMs: Math.max(1, Math.floor(timeoutMs)),
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
): Promise<void> {
  await risuai.addRisuReplacer('beforeRequest', beforeRequest);
  await risuai.addRisuChatListener('output', onOutput);
}
