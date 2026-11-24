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
