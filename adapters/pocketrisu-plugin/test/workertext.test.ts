import { describe, expect, it } from 'vitest';
import { workerLines, type WorkerStatus } from '../src/workertext';

const NOW = new Date(2026, 10, 24, 12, 0);  // local time, so the shown times hold in any time zone

function status(over: Partial<WorkerStatus> = {}): WorkerStatus {
  return { queued: { extract: 0, reveal: 0, summarize: 0, canon: 0, embed: 0 }, queued_total: 0, running: 0, retrying: 0,
    dead_recent: 0, done_recent: 0, recent_minutes: 30, dead_hours: 24, last_error: null, ...over };
}

const busy = status({ queued: { extract: 642, reveal: 0, summarize: 56, canon: 1010, embed: 0 }, queued_total: 1708,
  running: 2, retrying: 35, dead_recent: 1, done_recent: 96,
  last_error: { kind: 'canon', status: 'queued', at: new Date(2026, 10, 24, 9, 10).toISOString(), text: 'HTTP 504: upstream' } });

describe('workerLines (PHASE-61 S5)', () => {
  it('says nothing is waiting in one line when the worker is idle', () => {
    expect(workerLines('ko', status(), NOW)).toEqual({ level: 'idle', lines: ['모델 작업: 대기 없음'] });
    expect(workerLines('en', status(), NOW)).toEqual({ level: 'idle', lines: ['Model work: nothing waiting'] });
  });

  it('shows the queue by kind, the recent counts and the last error, with thousands separators', () => {
    expect(workerLines('ko', busy, NOW)).toEqual({ level: 'trouble', lines: [
      '대기 1,708건 (추출 642 · 요약 56 · canon 1,010) · 실행 중 2',
      '최근 30분: 완료 96건 · 재시도 중 35건 · 포기 1건(24시간)',
      '마지막 오류 09:10 (canon): HTTP 504: upstream'] });
    expect(workerLines('en', busy, NOW)).toEqual({ level: 'trouble', lines: [
      '1,708 waiting (extraction 642 · summaries 56 · canon 1,010) · 2 running',
      'Last 30 min: 96 finished · 35 being retried · 1 given up (24 h)',
      'Last error 09:10 (canon): HTTP 504: upstream'] });
  });

  it('leaves zero parts out and names other kinds by their own name', () => {
    const s = status({ queued: { extract: 0, reveal: 3, summarize: 0, canon: 0, embed: 1200, later_kind: 2 },
      queued_total: 1205, done_recent: 4 });
    expect(workerLines('ko', s, NOW)).toEqual({ level: 'working', lines: [
      '대기 1,205건 (공개 확인 3 · 임베딩 1,200 · later_kind 2)', '최근 30분: 완료 4건'] });
    expect(workerLines('en', status({ running: 1 }), NOW)).toEqual({ level: 'working', lines: ['1 running'] });
    expect(workerLines('en', status({ dead_recent: 2 }), NOW)).toEqual({ level: 'trouble', lines: [
      'Model work: nothing waiting', 'Last 30 min: 2 given up (24 h)'] });
  });

  it('puts the date before the time of an error from another day', () => {
    const s = status({ last_error: { kind: 'extract', status: 'dead', at: new Date(2026, 10, 22, 23, 5).toISOString(),
      text: 'HTTP 429' } });
    expect(workerLines('ko', s, NOW).lines[1]).toBe('마지막 오류 11-22 23:05 (추출): HTTP 429');
    expect(workerLines('en', s, NOW).lines[1]).toBe('Last error 11-22 23:05 (extraction): HTTP 429');
  });

  it('shows nothing, rather than throwing, for an answer it does not understand', () => {
    const empty = { level: 'idle', lines: [] };
    for (const odd of [null, undefined, 'x', [], {}, { ok: true }, { ...status(), running: '2' },
      { ...status(), queued: null }, { ...status(), queued: { extract: -1 } }, { ...status(), done_recent: undefined },
      { ...status(), last_error: { kind: 'canon' } }, { ...status(), last_error: { kind: 'c', status: 'dead', at: 'soon', text: '' } }]) {
      expect(workerLines('en', odd, NOW)).toEqual(empty);
    }
  });
});

describe('workerLines: the last hour of model calls (PHASE-61 S5+S6)', () => {
  const faults = { timeout: 0, transport: 0, bad_reply: 0, http_other: 0 };
  const calls = (over: Record<string, unknown> = {}) => ({ minutes: 60, total: 131, ok: 96, failed: 35,
    by_fault: { ...faults, '429': 6, '504': 29 }, median_ms: 3240, last_ok_at: null, last_failed_at: null, ...over });
  const queued = status({ queued: { extract: 3, reveal: 0, summarize: 0, canon: 0, embed: 0 }, queued_total: 3,
    done_recent: 4 });

  it('puts one line between the queue and the recent counts, the most frequent fault first', () => {
    expect(workerLines('ko', { ...queued, calls: calls() }, NOW)).toEqual({ level: 'working', lines: [
      '대기 3건 (추출 3)', '최근 1시간 호출: 성공 96 · 실패 35 (504 29 · 429 6) · 중간값 3.2초', '최근 30분: 완료 4건'] });
    expect(workerLines('en', { ...queued, calls: calls() }, NOW)).toEqual({ level: 'working', lines: [
      '3 waiting (extraction 3)', "Last hour's calls: 96 ok · 35 failed (504 29 · 429 6) · median 3.2 s",
      'Last 30 min: 4 finished'] });
  });

  it('names the faults, breaks a tie by name and uses thousands separators', () => {
    const c = calls({ total: 12_345, ok: 1_200, failed: 11_145, median_ms: 1_234_567,
      by_fault: { timeout: 3, transport: 1_100, bad_reply: 3, http_other: 2, '500': 10_037 } });
    expect(workerLines('ko', { ...status(), calls: c }, NOW).lines[1])
      .toBe('최근 1시간 호출: 성공 1,200 · 실패 11,145 (500 10,037 · 연결 실패 1,100 · 응답 오류 3 · 시간 초과 3 · 기타 HTTP 2)'
        + ' · 중간값 1,234.6초');
    expect(workerLines('en', { ...status(), calls: c }, NOW).lines[1])
      .toBe("Last hour's calls: 1,200 ok · 11,145 failed (500 10,037 · connection 1,100 · bad reply 3 · timeout 3"
        + ' · other HTTP 2) · median 1,234.6 s');
  });

  it('names another window in minutes, leaves out no failures and an unknown median', () => {
    const c = calls({ minutes: 30, total: 5, ok: 5, failed: 0, by_fault: faults, median_ms: null });
    expect(workerLines('ko', { ...status(), calls: c }, NOW).lines).toEqual(['모델 작업: 대기 없음', '최근 30분 호출: 성공 5']);
    expect(workerLines('en', { ...status(), calls: c }, NOW).lines).toEqual(['Model work: nothing waiting',
      "Last 30 min's calls: 5 ok"]);
    expect(workerLines('en', { ...status(), calls: calls({ median_ms: 60 }) }, NOW).lines[1]).toMatch(/ · median 0\.1 s$/);
  });

  it('is trouble when the model fails at least as often as it succeeds', () => {
    const level = (c: unknown) => workerLines('en', { ...queued, calls: c }, NOW).level;
    expect(level(calls())).toBe('working');  // 35 failed of 131
    expect(level(calls({ ok: 35 }))).toBe('trouble');
    expect(level(calls({ ok: 0, failed: 1, total: 1 }))).toBe('trouble');
    expect(level(calls({ ok: 0, failed: 0, total: 0 }))).toBe('working');
    expect(workerLines('en', { ...status(), calls: calls({ ok: 2, failed: 3, total: 5 }) }, NOW).level).toBe('trouble');
  });

  it('gives exactly the lines of today without calls, with none in the hour, or with calls it does not understand', () => {
    for (const s of [busy, queued, status()]) {
      const today = workerLines('en', s, NOW);
      for (const odd of [undefined, null, 'x', [], 7, {}, calls({ total: 0, ok: 0, failed: 0 }), calls({ total: '131' }),
        calls({ ok: -1 }), calls({ minutes: 0 }), calls({ by_fault: null }), calls({ by_fault: { '429': 'six' } }),
        calls({ median_ms: 'slow' }), calls({ failed: undefined })]) {
        expect(workerLines('en', { ...s, calls: odd }, NOW)).toEqual(today);
      }
    }
  });
});
