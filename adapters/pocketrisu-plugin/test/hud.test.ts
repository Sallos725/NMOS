import { describe, expect, it } from 'vitest';
import { DONE_MS, EMPTY, nextChange, OUTCOME_MS, parseCoverage, reduce, view, type Coverage, type HudEvent, type HudState } from '../src/hud';

const coverage = (extract: [number, number, number, number] | null, embed: [number, number, number, number] | null): Coverage => ({
  extract: extract && { done: extract[0], total: extract[1], pending: extract[2], failed: extract[3] },
  embed: embed && { done: embed[0], total: embed[1], pending: embed[2], failed: embed[3] },
});

function run(events: [HudEvent, number][]): HudState {
  return events.reduce((s, [e, at]) => reduce(s, e, at), EMPTY);
}

describe('request outcome', () => {
  it('shows a running request without a bar', () => {
    const s = run([[{ type: 'request-start' }, 0]]);
    expect(view(s, 0, 'ko')).toEqual({ kind: 'busy', text: '🧠 기억 불러오는 중…', fraction: null });
  });

  it('shows each outcome, then hides it', () => {
    const end = (outcome: 'injected' | 'nothing-relevant' | 'failed', error?: string, deadlineMs = 3000) =>
      run([[{ type: 'request-start' }, 0], [{ type: 'request-end', outcome, chars: 1234, error, deadlineMs, conversationId: 'c' }, 100]]);
    expect(view(end('injected'), 100, 'ko')).toMatchObject({ kind: 'ok', text: '✓ 기억 주입 (1234자)' });
    expect(view(end('nothing-relevant'), 100, 'ko')).toMatchObject({ kind: 'muted', text: '– 관련 기억 없음' });
    expect(view(end('failed', 'deadline during /v1/retrieve'), 100, 'ko'))
      .toMatchObject({ kind: 'warn', text: '⚠ 건너뜀: 제한 시간 3초 초과 · 눌러서 늘리기' });
    expect(view(end('failed', 'deadline during /v1/retrieve', 2500), 100, 'en'))
      .toMatchObject({ kind: 'warn', text: '⚠ Skipped: over the 2.5 s deadline · tap to raise' });
    expect(view(end('failed', '/v1/retrieve -> HTTP 500'), 100, 'ko')).toMatchObject({ kind: 'warn', text: '⚠ 건너뜀: 사이드카 오류' });
    expect(view(end('injected'), 100 + OUTCOME_MS, 'ko')).toBeNull();
  });

  it('an abandoned request clears the running pill but not a finished one', () => {
    expect(view(run([[{ type: 'request-start' }, 0], [{ type: 'request-abandon' }, 1]]), 1, 'ko')).toBeNull();
    const done = run([[{ type: 'request-end', outcome: 'injected', chars: 5, conversationId: null }, 0], [{ type: 'request-abandon' }, 1]]);
    expect(view(done, 1, 'ko')?.kind).toBe('ok');
  });

  it('speaks English', () => {
    const s = run([[{ type: 'request-end', outcome: 'injected', chars: 12, conversationId: null }, 0]]);
    expect(view(s, 0, 'en')?.text).toBe('✓ Memory injected (12 chars)');
    expect(view(run([[{ type: 'request-start' }, 0]]), 0, 'en')?.text).toBe('🧠 Recalling memory…');
  });
});

describe('background progress', () => {
  it('shows counts and a bar while work is pending', () => {
    const s = run([[{ type: 'coverage', coverage: coverage([132, 480, 348, 0], [480, 480, 0, 0]) }, 0]]);
    expect(view(s, 0, 'ko')).toEqual({ kind: 'busy', text: '추출 132/480 · 임베딩 480/480', fraction: (132 + 480) / 960 });
  });

  it('lists only generations that exist and appends failures', () => {
    const s = run([[{ type: 'coverage', coverage: coverage([10, 40, 27, 3], null) }, 0]]);
    expect(view(s, 0, 'ko')?.text).toBe('추출 10/40 · ⚠ 실패 3');
    expect(view(s, 0, 'en')?.text).toBe('Facts 10/40 · ⚠ 3 failed');
  });

  it('a request outcome shows over the progress, then the progress returns', () => {
    const s = run([
      [{ type: 'coverage', coverage: coverage([1, 4, 3, 0], null) }, 0],
      [{ type: 'request-end', outcome: 'nothing-relevant', chars: 0, conversationId: 'c' }, 10],
    ]);
    expect(view(s, 10, 'ko')?.text).toBe('– 관련 기억 없음');
    expect(view(s, 10 + OUTCOME_MS, 'ko')?.text).toBe('추출 1/4');
  });

  it('says done briefly when shown work finishes', () => {
    const s = run([
      [{ type: 'coverage', coverage: coverage([1, 4, 3, 0], null) }, 0],
      [{ type: 'coverage', coverage: coverage([4, 4, 0, 0], null) }, 3000],
    ]);
    expect(view(s, 3000, 'ko')).toEqual({ kind: 'ok', text: '✓ 처리 완료', fraction: 1 });
    expect(view(s, 3000 + DONE_MS, 'ko')).toBeNull();
  });

  it('shows nothing when nothing was pending', () => {
    expect(view(run([[{ type: 'coverage', coverage: coverage([4, 4, 0, 0], [4, 4, 0, 0]) }, 0]]), 0, 'ko')).toBeNull();
  });

  it('reset clears everything', () => {
    const s = run([[{ type: 'coverage', coverage: coverage([1, 4, 3, 0], null) }, 0], [{ type: 'reset' }, 1]]);
    expect(view(s, 1, 'ko')).toBeNull();
  });
});

describe('nextChange', () => {
  it('returns the earliest future expiry', () => {
    const s = run([
      [{ type: 'coverage', coverage: coverage([1, 4, 3, 0], null) }, 0],
      [{ type: 'coverage', coverage: coverage([4, 4, 0, 0], null) }, 100],
      [{ type: 'request-end', outcome: 'injected', chars: 1, conversationId: null }, 200],
    ]);
    expect(nextChange(s, 200)).toBe(100 + DONE_MS);
    expect(nextChange(s, 100 + DONE_MS)).toBe(200 + OUTCOME_MS);
    expect(nextChange(s, 200 + OUTCOME_MS)).toBeNull();
    expect(nextChange(EMPTY, 0)).toBeNull();
  });
});

describe('parseCoverage', () => {
  it('maps the sidecar coverage view', () => {
    const json = {
      extraction: { generation: { key: 'x' }, eligible: 40, compiled: 10, pending: 27, failed: 3, historical_only: 0 },
      embeddings: { generation: null },
    };
    expect(parseCoverage(json)).toEqual({ extract: { done: 10, total: 40, pending: 27, failed: 3 }, embed: null });
  });

  it('treats a chat without rows or a malformed body as nothing', () => {
    expect(parseCoverage({ extraction: { generation: { key: 'x' } }, embeddings: { generation: { key: 'y' } } }))
      .toEqual({ extract: null, embed: null });
    expect(parseCoverage(null)).toEqual({ extract: null, embed: null });
  });
});
