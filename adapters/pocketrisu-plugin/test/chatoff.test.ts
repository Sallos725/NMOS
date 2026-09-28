import { describe, expect, it } from 'vitest';
import { CHAT_OFF_ARG, createChatSwitch, formatChatIds, parseChatIds, withChat } from '../src/chatoff';

describe('the list of chats NMOS is off for (ADR 0048)', () => {
  it('reads ids separated by spaces, commas or lines, once each', () => {
    expect(parseChatIds('')).toEqual([]);
    expect(parseChatIds(' a b\nc,a ,, ')).toEqual(['a', 'b', 'c']);
  });

  it('adds and removes one chat and leaves the others', () => {
    expect(withChat(['a', 'b'], 'c', true)).toEqual(['a', 'b', 'c']);
    expect(withChat(['a', 'b'], 'b', true)).toEqual(['a', 'b']);
    expect(withChat(['a', 'b'], 'a', false)).toEqual(['b']);
    expect(formatChatIds(['a', 'b'])).toBe('a b');
  });
});

describe('createChatSwitch', () => {
  function make(chatId: string | null, stored = '') {
    const args: Record<string, string> = { [CHAT_OFF_ARG]: stored };
    let writes = 0;
    const open = { id: chatId };
    const sw = createChatSwitch({
      getArg: async (key) => { await new Promise((r) => setTimeout(r, 1)); return args[key] ?? ''; },
      setArg: async (key, value) => { await new Promise((r) => setTimeout(r, 1)); writes += 1; args[key] = value; },
      currentChatId: async () => open.id,
    });
    return { sw, args, open, writes: () => writes };
  }

  it('turns the open chat off and back on, keeping the other chats', async () => {
    const { sw, args } = make('c1', 'c0');
    expect(await sw.current()).toEqual({ id: 'c1', off: false });
    expect(await sw.toggle()).toEqual({ id: 'c1', off: true });
    expect(args[CHAT_OFF_ARG]).toBe('c0 c1');
    expect(await sw.current()).toEqual({ id: 'c1', off: true });
    expect(await sw.toggle()).toEqual({ id: 'c1', off: false });
    expect(args[CHAT_OFF_ARG]).toBe('c0');
  });

  it('sets the chat it is given, whichever is open, and writes only a change', async () => {
    const { sw, args, open, writes } = make('c1');
    open.id = 'c2';
    expect(await sw.set('c1', true)).toEqual({ id: 'c1', off: true });
    expect(await sw.set('c1', true)).toEqual({ id: 'c1', off: true });
    expect(args[CHAT_OFF_ARG]).toBe('c1');
    expect(writes()).toBe(1);
  });

  it('takes two quick taps one after the other', async () => {
    const { sw, args } = make('c1');
    const [first, second] = await Promise.all([sw.toggle(), sw.toggle()]);
    expect([first.off, second.off]).toEqual([true, false]);
    expect(args[CHAT_OFF_ARG]).toBe('');
  });

  it('does nothing without an open chat', async () => {
    const { sw, writes } = make(null, 'c0');
    expect(await sw.current()).toEqual({ id: null, off: false });
    expect(await sw.toggle()).toEqual({ id: null, off: false });
    expect(writes()).toBe(0);
  });

  it('a failed write does not stop the next change', async () => {
    let fail = true;
    const args: Record<string, string> = {};
    const sw = createChatSwitch({
      getArg: async (key) => args[key] ?? '',
      setArg: async (key, value) => { if (fail) throw new Error('host refused'); args[key] = value; },
      currentChatId: async () => 'c1',
    });
    await expect(sw.toggle()).rejects.toThrow('host refused');
    fail = false;
    expect(await sw.toggle()).toEqual({ id: 'c1', off: true });
  });
});
