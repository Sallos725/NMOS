import { afterEach, describe, expect, it, vi } from 'vitest';
import { MAX_DEADLINE_MS, MAX_RESERVED_TOKENS } from '../src/form';
import { chatSwitchNotice, registerHooks, risuChatSwitch, risuHost } from '../src/host';

function withArgs(args: Record<string, string | number>) {
  (globalThis as { risuai?: unknown }).risuai = { getArgument: async (key: string) => args[key.split('::').pop()!] };
}

afterEach(() => { delete (globalThis as { risuai?: unknown }).risuai; });

describe('plugin arguments', () => {
  it('keep the deadline and the memory budget within their limits when set outside the panel', async () => {
    withArgs({ deadline_ms: 999_999, reserved_memory_tokens: 50_000 });
    const s = await risuHost.settings();
    expect([s.deadlineMs, s.reservedMemoryTokens]).toEqual([MAX_DEADLINE_MS, MAX_RESERVED_TOKENS]);
    withArgs({ deadline_ms: 0, reserved_memory_tokens: 0 });  // PocketRisu's unset int
    const d = await risuHost.settings();
    expect([d.deadlineMs, d.reservedMemoryTokens]).toEqual([3000, 2000]);
  });
});

describe('chats NMOS is off for (ADR 0048)', () => {
  it('are read from their plugin arg', async () => {
    withArgs({ disabled_chats: 'a  b,c a' });
    expect((await risuHost.settings()).offChats).toEqual(['a', 'b', 'c']);
    withArgs({});
    expect((await risuHost.settings()).offChats).toEqual([]);
  });
});

describe('menus', () => {
  it('open the panel from the sidebar menu and switch this chat from the chat menu (ADR 0048)', async () => {
    const args: Record<string, string | number> = { language: 'en' };
    const buttons: { arg: { name: string; location?: string; id?: string }; callback: () => unknown }[] = [];
    const alerts: string[] = [];
    (globalThis as { risuai?: unknown }).risuai = {
      getArgument: async (key: string) => args[key],
      setArgument: async (key: string, value: string | number) => { args[key] = value; },
      addRisuReplacer: async () => {},
      addRisuChatListener: async () => {},
      registerSetting: async () => {},
      registerButton: async (arg: { name: string; location?: string; id?: string }, callback: () => unknown) => {
        buttons.push({ arg, callback });
      },
      alert: async (message: string) => { alerts.push(message); },
      getCurrentCharacterIndex: async () => 0,
      getCurrentChatIndex: async () => 0,
      getChatFromIndex: async () => ({ id: 'chat-9', message: [] }),
    };
    const hud = { enable: async () => 'unsupported' as const, disable: async () => {}, problem: () => null, background: () => {} };
    await registerHooks(async (p) => p, () => {}, async () => ({} as never), async () => ({} as never), hud);
    expect(buttons.map((b) => [b.arg.location, b.arg.id])).toEqual([
      ['chat', 'nmos-chat'], ['chat', 'nmos-chat-switch'], ['hamburger', 'nmos-sidebar']]);
    const toggle = buttons.find((b) => b.arg.id === 'nmos-chat-switch')!;
    toggle.callback();
    await vi.waitFor(() => expect(alerts).toHaveLength(1));
    expect(args.disabled_chats).toBe('chat-9');
    expect(alerts[0]).toMatch(/^NMOS is off for this chat/);
    expect(await risuChatSwitch.current()).toEqual({ id: 'chat-9', off: true });
    toggle.callback();
    await vi.waitFor(() => expect(alerts).toHaveLength(2));
    expect(args.disabled_chats).toBe('');
    expect(alerts[1]).toMatch(/^NMOS is back on/);
  });

  it('says a chat turned back on still gets nothing while NMOS is off for every chat', () => {
    expect(chatSwitchNotice('en', { id: 'c', off: false }, false)).toMatch(/off for every chat/);
    expect(chatSwitchNotice('en', { id: 'c', off: false }, true)).toMatch(/^NMOS is back on/);
    expect(chatSwitchNotice('en', { id: 'c', off: true }, false)).toMatch(/^NMOS is off for this chat/);
    expect(chatSwitchNotice('en', { id: null, off: false }, true)).toMatch(/^No chat is open/);
  });

  it('the switch has nothing to do when no character is open', async () => {
    (globalThis as { risuai?: unknown }).risuai = { getCurrentCharacterIndex: async () => -1, getArgument: async () => '' };
    expect(await risuChatSwitch.toggle()).toEqual({ id: null, off: false });
  });
});
