import { describe, expect, it } from 'vitest';
import { budgetAdvice, FIT_CAP } from '../src/budget';

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
