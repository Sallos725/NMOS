// Budget advice (Phase 10, ADR 0036): when the last request left memory out for lack of room, say how much and
// suggest the memory budget that holds it all. Pure; the status tab shows it.

/** `memory` of a `/v1/retrieve` answer: memory lines offered, those left out for the budget, and the smallest
 *  budget (in 100s, up to FIT_CAP) that holds them all; null when none were left out or more is needed. */
export interface MemoryFit {
  offered: number;
  cut: number;
  fits_at: number | null;
}

export const FIT_CAP = 6000;  // as the sidecar's (packet.FIT_CAP)

export interface BudgetAdvice {
  cut: number;
  offered: number;
  budget: number;
  suggest: number;
  /** False when even FIT_CAP leaves some out: the suggestion then only holds more. */
  all: boolean;
}

export interface RequestMemory {
  outcome: 'injected' | 'nothing-relevant' | 'failed';
  budgetTokens?: number;
  memory?: MemoryFit | null;
}

export function budgetAdvice(r: RequestMemory | null | undefined, current?: number): BudgetAdvice | null {
  if (!r || r.outcome === 'failed' || !r.memory || !(r.memory.cut > 0) || !(r.budgetTokens && r.budgetTokens > 0)) return null;
  const all = typeof r.memory.fits_at === 'number';
  const suggest = all ? r.memory.fits_at as number : FIT_CAP;
  // Nothing to suggest past the cap, or once the budget was raised to it (it applies from the next request).
  if (suggest <= r.budgetTokens || (current !== undefined && current >= suggest)) return null;
  return { cut: r.memory.cut, offered: r.memory.offered, budget: r.budgetTokens, suggest, all };
}
