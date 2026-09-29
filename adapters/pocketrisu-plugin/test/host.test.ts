import { afterEach, describe, expect, it, vi } from 'vitest';
import { MAX_DEADLINE_MS, MAX_RESERVED_TOKENS } from '../src/form';
import { chatSwitchNotice, registerHooks, risuChatSwitch, risuHost } from '../src/host';
import { NMOS_ICON, namedIcon } from '../src/icon';

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
    expect([d.deadlineMs, d.reservedMemoryTokens]).toEqual([3000, 4000]);
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
    const buttons: { arg: { name: string; icon: string; location?: string; id?: string }; callback: () => unknown }[] = [];
    const settingIcons: unknown[] = [];
    const alerts: string[] = [];
    (globalThis as { risuai?: unknown }).risuai = {
      getArgument: async (key: string) => args[key],
      setArgument: async (key: string, value: string | number) => { args[key] = value; },
      addRisuReplacer: async () => {},
      addRisuChatListener: async () => {},
      registerSetting: async (_name: string, _callback: unknown, icon?: string) => { settingIcons.push(icon); },
      registerButton: async (arg: { name: string; icon: string; location?: string; id?: string }, callback: () => unknown) => {
        buttons.push({ arg, callback });
      },
      alert: async (message: string) => { alerts.push(message); },
      getCurrentCharacterIndex: async () => 0,
      getCurrentChatIndex: async () => 0,
      getChatFromIndex: async () => ({ id: 'chat-9', message: [] }),
    };
    const hud = { enable: async () => 'unsupported' as const, disable: async () => {}, problem: () => null, background: () => {} };
    await registerHooks(async (p) => p, () => {}, async () => ({} as never), async () => ({} as never),
      async () => new ArrayBuffer(0), hud);
    expect(buttons.map((b) => [b.arg.location, b.arg.id])).toEqual([
      ['chat', 'nmos-chat'], ['chat', 'nmos-chat-switch'], ['hamburger', 'nmos-sidebar']]);
    // The panel's three entries carry NMOS's icon; the sidebar shows no name, so there the icon carries it.
    expect(settingIcons).toEqual([NMOS_ICON]);
    expect(buttons.filter((b) => b.arg.id !== 'nmos-chat-switch').map((b) => b.arg.icon))
      .toEqual([NMOS_ICON, namedIcon('NMOS memory')]);
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

describe('archive files (ADR 0050, H21)', () => {
  it('are fetched through nativeFetch on the route as bytes, and an error answer as its JSON', async () => {
    const calls: [string, Record<string, unknown>][] = [];
    const zip = new Uint8Array([80, 75, 3, 4, 0]);
    let answer: { status: number; body: Uint8Array } = { status: 200, body: zip };
    (globalThis as { risuai?: unknown }).risuai = {
      nativeFetch: async (url: string, options: Record<string, unknown>) => {
        calls.push([url, options]);
        return new Response(answer.body, { status: answer.status });
      },
    };
    const ok = await risuHost.requestFile!('http://nmos:8790/v1/archive', { Authorization: 'Bearer t' }, 300_000, 'server');
    expect(ok.status).toBe(200);
    expect(new Uint8Array(ok.bytes!)).toEqual(zip);
    expect(calls[0]).toEqual(['http://nmos:8790/v1/archive', { method: 'GET', headers: { Authorization: 'Bearer t' },
      requestTimeoutMs: 300_000, networkRoute: 'local_network' }]);
    answer = { status: 409, body: new TextEncoder().encode('{"detail":"refused"}') };
    expect(await risuHost.requestFile!('http://127.0.0.1:8790/v1/archive', {}, 1000, 'direct'))
      .toEqual({ status: 409, bytes: null, json: { detail: 'refused' } });
    expect(calls[1]?.[1]).not.toHaveProperty('networkRoute');
  });
});
