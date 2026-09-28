// Chats the owner switched NMOS off for (ADR 0048): one plugin arg holding their host chat ids. A chat on the
// list is passed through untouched and nothing of it leaves the host; what the sidecar already keeps of it stays.

/** The plugin arg that holds the list (ids separated by spaces). */
export const CHAT_OFF_ARG = 'disabled_chats';

export function parseChatIds(value: string): string[] {
  return [...new Set(value.split(/[\s,]+/).filter(Boolean))];
}

/** The list with `chatId` switched off (`off`) or back on. */
export function withChat(ids: string[], chatId: string, off: boolean): string[] {
  const rest = ids.filter((id) => id !== chatId);
  return off ? [...rest, chatId] : rest;
}

export function formatChatIds(ids: string[]): string {
  return ids.join(' ');
}

export interface ChatState {
  /** The chat open now; null when none is. */
  id: string | null;
  off: boolean;
}

/** The chat open now, switched off and on from the panel and the menus. */
export interface ChatSwitch {
  current(): Promise<ChatState>;
  /** Switch NMOS off (`true`) or back on for chat `id` (the one the panel shows); its state after. */
  set(id: string, off: boolean): Promise<ChatState>;
  /** Flip it for the chat open now; its state after. */
  toggle(): Promise<ChatState>;
}

export interface ChatSwitchDeps {
  getArg(key: string): Promise<string>;
  setArg(key: string, value: string): Promise<void>;
  currentChatId(): Promise<string | null>;
}

export function createChatSwitch(deps: ChatSwitchDeps): ChatSwitch {
  let queue: Promise<unknown> = Promise.resolve();
  // Changes run one at a time: two quick taps must not both read the list before either writes it.
  function serial<T>(task: () => Promise<T>): Promise<T> {
    const next = queue.then(task, task);
    queue = next.catch(() => {});
    return next;
  }

  async function current(): Promise<ChatState> {
    const id = await deps.currentChatId();
    return { id, off: id !== null && parseChatIds(await deps.getArg(CHAT_OFF_ARG)).includes(id) };
  }

  async function write(id: string, off: boolean): Promise<ChatState> {
    const ids = parseChatIds(await deps.getArg(CHAT_OFF_ARG));
    if (ids.includes(id) !== off) await deps.setArg(CHAT_OFF_ARG, formatChatIds(withChat(ids, id, off)));
    return { id, off };
  }

  return {
    current: () => serial(current),
    set: (id, off) => serial(() => write(id, off)),
    toggle: () => serial(async () => {
      const now = await current();
      return now.id === null ? now : write(now.id, !now.off);
    }),
  };
}
