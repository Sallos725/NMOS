import { describe, expect, it } from 'vitest';
import { budgetAdvice, estimateTokens, FIT_CAP } from '../src/budget';
import { GUARD_LINE, GUARD_RESERVE_TOKENS } from '../src/prompt';

const cut = { outcome: 'injected' as const, budgetTokens: 800, memory: { offered: 15, cut: 4, fits_at: 1100 } };

describe('budget advice (ADR 0036)', () => {
  it('suggests the budget that holds every memory line', () => {
    expect(budgetAdvice(cut)).toEqual({ cut: 4, offered: 15, budget: 800, suggest: 1100, all: true });
  });

  it('suggests the cap when even that leaves some out', () => {
    expect(budgetAdvice({ ...cut, memory: { offered: 60, cut: 30, fits_at: null } }))
      .toEqual({ cut: 30, offered: 60, budget: 800, suggest: FIT_CAP, all: false });
  });

  it('says nothing when nothing was left out, the request failed, the sidecar is older, or the budget was raised', () => {
    expect(budgetAdvice({ ...cut, memory: { offered: 9, cut: 0, fits_at: null } })).toBeNull();
    expect(budgetAdvice({ ...cut, outcome: 'failed' })).toBeNull();
    expect(budgetAdvice({ outcome: 'injected', budgetTokens: 800 })).toBeNull();
    expect(budgetAdvice(null)).toBeNull();
    expect(budgetAdvice(cut, 1100)).toBeNull();  // raised already: applies from the next reply
    expect(budgetAdvice({ ...cut, budgetTokens: FIT_CAP, memory: { offered: 60, cut: 30, fits_at: null } })).toBeNull();
  });
});

describe('token estimate (Phase 60)', () => {
  it('estimates ASCII, non-ASCII, surrogate pairs, and mixed text at the packet-policy rate', () => {
    expect(estimateTokens('')).toBe(0);
    expect(estimateTokens('abcdefg')).toBe(2);
    expect(estimateTokens('세라')).toBe(3);
    // 9 ASCII (' said hi!') / 3.5 + 2 non-ASCII ('세라') * 1.2 = 4.9714... -> 5
    expect(estimateTokens('세라 said hi!')).toBe(5);
    // Surrogate pair counts once as non-ASCII: ceil(1.2) = 2 (not ceil(2.4) = 3).
    expect(estimateTokens('😀')).toBe(2);
  });

  it('fits the guard line inside GUARD_RESERVE_TOKENS', () => {
    expect(estimateTokens(`\n${GUARD_LINE}`)).toBeLessThanOrEqual(GUARD_RESERVE_TOKENS);
  });
});
