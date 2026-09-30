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
    expect(view(s, 0, 'ko')).toEqual({ kind: 'busy', text: '기억 불러오는 중…', fraction: null, icon: true });
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

  it('says so when NMOS is off for the chat (ADR 0048)', () => {
    const s = run([[{ type: 'request-start' }, 0],
      [{ type: 'request-end', outcome: 'chat-off', chars: 0, conversationId: null }, 10]]);
    expect(view(s, 10, 'ko')).toEqual({ kind: 'muted', text: '⏻ 이 채팅은 NMOS 꺼짐', fraction: null });
    expect(view(s, 10, 'en')?.text).toBe('⏻ NMOS is off for this chat');
    expect(view(s, 10 + OUTCOME_MS, 'ko')).toBeNull();
  });

  it('an abandoned request clears the running pill but not a finished one', () => {
    expect(view(run([[{ type: 'request-start' }, 0], [{ type: 'request-abandon' }, 1]]), 1, 'ko')).toBeNull();
    const done = run([[{ type: 'request-end', outcome: 'injected', chars: 5, conversationId: null }, 0], [{ type: 'request-abandon' }, 1]]);
    expect(view(done, 1, 'ko')?.kind).toBe('ok');
  });

  it('speaks English', () => {
    const s = run([[{ type: 'request-end', outcome: 'injected', chars: 12, conversationId: null }, 0]]);
    expect(view(s, 0, 'en')?.text).toBe('✓ Memory injected (12 chars)');
    expect(view(run([[{ type: 'request-start' }, 0]]), 0, 'en')?.text).toBe('Recalling memory…');
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

describe('what the display says about served memory and finished work (PHASE-17 Q5, Q6)', () => {
  const end = (extra: object) => reduce(EMPTY, { type: 'request-end', outcome: 'injected', chars: 812, conversationId: 'c',
    ...extra }, 0);
  it('says a packet was reused or recalled without vectors, as a plain success', () => {
    expect(view(end({ reused: true }), 1, 'ko')).toEqual({ kind: 'ok', text: '✓ 기억 주입 (812자) · 재사용', fraction: null });
    expect(view(end({ vectors: 'fallback' }), 1, 'en')?.text).toBe('✓ Memory injected (812 chars) · lexical only');
    expect(view(end({ reused: true, vectors: 'fallback' }), 1, 'en'))
      .toMatchObject({ kind: 'ok', text: '✓ Memory injected (812 chars) · reused · lexical only' });
    expect(view(end({ vectors: 'on' }), 1, 'en')?.text).toBe('✓ Memory injected (812 chars)');
  });
  const cov = (pendingN: number, produced: object | null) => ({
    extract: { done: 3, total: 5, pending: pendingN, failed: 0 }, embed: null, produced } as Coverage);
  it('says what the finished work added, counted from when it was first seen', () => {
    let s = reduce(EMPTY, { type: 'coverage', coverage: cov(2, { facts: 40, summaries: 2 }) }, 0);
    s = reduce(s, { type: 'coverage', coverage: cov(1, { facts: 44, summaries: 2 }) }, 1);
    s = reduce(s, { type: 'coverage', coverage: cov(0, { facts: 47, summaries: 3 }) }, 2);
    expect(view(s, 3, 'ko')?.text).toBe('✓ 사실 7개 추가 · 요약 1개 추가');
    expect(view(s, 3, 'en')?.text).toBe('✓ facts +7 · summaries +1');
  });
  it('waits for summaries, which run last, before it says what was made (Copilot review)', () => {
    const c = (pendingN: number, sums: number, produced: object) => ({ extract: { done: 5, total: 5, pending: pendingN,
      failed: 0 }, embed: null, produced, summarize: { pending: sums, failed: 0 } } as Coverage);
    let s = reduce(EMPTY, { type: 'coverage', coverage: c(1, 0, { facts: 10, summaries: 2 }) }, 0);
    s = reduce(s, { type: 'coverage', coverage: c(0, 1, { facts: 12, summaries: 2 }) }, 1);
    expect(view(s, 2, 'en')?.text).toBe('Facts 5/5 · summaries to write: 1');
    s = reduce(s, { type: 'coverage', coverage: c(0, 0, { facts: 12, summaries: 3 }) }, 3);
    expect(view(s, 4, 'en')?.text).toBe('✓ facts +2 · summaries +1');
  });
  it('says so when the work it waited for failed at the end (Copilot re-review)', () => {
    const c = (sums: number, failed: number, produced: object) => ({ extract: { done: 5, total: 5, pending: 0, failed: 1 },
      embed: null, produced, summarize: { pending: sums, failed } } as Coverage);
    let s = reduce(EMPTY, { type: 'coverage', coverage: c(1, 0, { facts: 10, summaries: 2 }) }, 0);  // 1 old failure
    s = reduce(s, { type: 'coverage', coverage: c(0, 1, { facts: 12, summaries: 2 }) }, 1);
    expect(view(s, 2, 'en')).toMatchObject({ kind: 'warn', text: '⚠ 1 failed · facts +2' });
    s = reduce(EMPTY, { type: 'coverage', coverage: c(1, 0, { facts: 10, summaries: 2 }) }, 0);
    s = reduce(s, { type: 'coverage', coverage: c(0, 0, { facts: 10, summaries: 3 }) }, 1);
    expect(view(s, 2, 'en')).toMatchObject({ kind: 'ok', text: '✓ summaries +1' });  // the old failure is not news
  });
  it('says only "done" when nothing was added or an older sidecar does not count', () => {
    let s = reduce(EMPTY, { type: 'coverage', coverage: cov(1, { facts: 40, summaries: 2 }) }, 0);
    s = reduce(s, { type: 'coverage', coverage: cov(0, { facts: 38, summaries: 2 }) }, 1);  // a turn re-extracted
    expect(view(s, 2, 'en')?.text).toBe('✓ Processing done');
    s = reduce(EMPTY, { type: 'coverage', coverage: cov(1, null) }, 0);
    s = reduce(s, { type: 'coverage', coverage: cov(0, null) }, 1);
    expect(view(s, 2, 'en')?.text).toBe('✓ Processing done');
  });
});

describe('parseCoverage', () => {
  it('maps the sidecar coverage view', () => {
    const json = {
      extraction: { generation: { key: 'x' }, eligible: 40, compiled: 10, pending: 27, failed: 3, historical_only: 0 },
      embeddings: { generation: null },
    };
    expect(parseCoverage(json)).toEqual({ extract: { done: 10, total: 40, pending: 27, failed: 3 }, embed: null,
      produced: null, summarize: null });
    expect(parseCoverage({ ...json, summaries: { pending: 2, failed: 1 } }).summarize).toEqual({ pending: 2, failed: 1 });
    expect(parseCoverage({ ...json, produced: { facts: 12, summaries: 1 } }).produced).toEqual({ facts: 12, summaries: 1 });
  });

  it('treats a chat without rows or a malformed body as nothing', () => {
    expect(parseCoverage({ extraction: { generation: { key: 'x' } }, embeddings: { generation: { key: 'y' } } }))
      .toEqual({ extract: null, embed: null, produced: null, summarize: null });
    expect(parseCoverage(null)).toEqual({ extract: null, embed: null, produced: null, summarize: null });
    expect(parseCoverage({ produced: { facts: '3' } }).produced).toBeNull();
  });
});
