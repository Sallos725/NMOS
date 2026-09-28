import { afterEach, describe, expect, it } from 'vitest';
import { MAX_DEADLINE_MS, MAX_RESERVED_TOKENS } from '../src/form';
import { risuHost } from '../src/host';

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
