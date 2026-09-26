import { describe, expect, it } from 'vitest';
import { deadlineAdvice } from '../src/deadline';

const over = { outcome: 'failed' as const, error: 'deadline during /v1/retrieve', ms: 3001, deadlineMs: 3000 };

describe('deadline advice (owner decision on audit A-09)', () => {
  it('past the deadline: suggests 1.25× what the request took, rounded up to 500 ms', () => {
    expect(deadlineAdvice({ ...over, neededMs: 3292 })).toEqual({ level: 'over', deadlineMs: 3000, tookMs: 3292, suggestMs: 4500 });
  });

  it('past the deadline with no measurement: at least 1.25× the deadline', () => {
    expect(deadlineAdvice(over)).toEqual({ level: 'over', deadlineMs: 3000, tookMs: null, suggestMs: 4000 });
  });

  it('close to the deadline: 80 % of it or more', () => {
    expect(deadlineAdvice({ outcome: 'injected', ms: 2500, deadlineMs: 3000 }))
      .toEqual({ level: 'near', deadlineMs: 3000, tookMs: 2500, suggestMs: 3500 });
    expect(deadlineAdvice({ outcome: 'nothing-relevant', ms: 2790, deadlineMs: 3000 })).toMatchObject({ level: 'near', suggestMs: 3500 });
  });

  it('nothing to say when well within, or when a request failed for another reason', () => {
    expect(deadlineAdvice({ outcome: 'injected', ms: 2300, deadlineMs: 3000 })).toBeNull();
    expect(deadlineAdvice({ outcome: 'failed', error: '/v1/retrieve -> HTTP 500', ms: 40, deadlineMs: 3000 })).toBeNull();
    expect(deadlineAdvice(null)).toBeNull();
  });

  it('never suggests more than the 30 s maximum', () => {
    expect(deadlineAdvice({ ...over, deadlineMs: 29_000, neededMs: 40_000 })?.suggestMs).toBe(30_000);
  });
});
