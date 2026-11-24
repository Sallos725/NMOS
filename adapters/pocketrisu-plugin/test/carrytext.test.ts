import { describe, expect, it } from 'vitest';
import {
  carryCountsLine, carryCutoffLabel, carryErrorText, carryRefusal, carrySourceLabel,
  isCarryConflict, isCarryNotFound, parseCutoffTurn,
} from '../src/carrytext';
import { createAdapter, type HostPort } from '../src/core';
import { t, type Lang } from '../src/i18n';

function uiErrorText(lang: Lang, error: unknown): string {
  const text = error instanceof Error ? error.message : String(error);
  return text.replace(/^\/v1\/\S+ -> HTTP 422: /, t(lang, 'invalid')).replace(/^\/v1\/\S+ -> /, t(lang, 'sidecar_error'));
}

describe('carryRefusal (PHASE-60 S6)', () => {
  const cases: [string, { rows: number; max: number } | null][] = [
    ['too_many_rows: rows=2400 max=2000 (the reading holds 2400 rows; a link carries at most 2000)', { rows: 2400, max: 2000 }],
    ['/v1/conversations/c1/carry/preview -> HTTP 422: too_many_rows: rows=2400 max=2000 (the reading holds 2400 rows; a link carries at most 2000)', { rows: 2400, max: 2000 }],
    ['/v1/conversations/c1/carry -> HTTP 422: too_many_rows: rows=2001 max=2000 (too large)', { rows: 2001, max: 2000 }],
    ['too_many_rows: rows=501 max=500', { rows: 501, max: 500 }],
    // The sentence without the marker is not a size refusal: only the marker is read
    ['the reading holds 2345 rows; a link carries at most 2000', null],
    ['/v1/conversations/c1/carry/preview -> HTTP 422: the reading holds 2001 rows; a link carries at most 2000', null],
    // JSON form is not accepted
    ['{"code":"too_many_rows","rows":2400,"max":2000}', null],
    ['/v1/conversations/c1/carry/preview -> HTTP 422: {"code":"too_many_rows","rows":2400,"max":2000}', null],
    // Non-leading marker or other errors
    ['note: too_many_rows: rows=2400 max=2000', null],
    ['/v1/conversations/c1/carry/preview -> HTTP 422: the source has no messages', null],
    ['/v1/conversations/c1/carry/preview -> HTTP 422: a chat never carries itself', null],
    ['/v1/conversations/c1/carry/preview -> HTTP 422: regression mode needs 1 to 8 character names', null],
    ['/v1/conversations/c1/carry/preview -> HTTP 404: Not Found', null],
    ['', null],
  ];

  it('matches the too_many_rows marker and returns null otherwise', () => {
    for (const [input, expected] of cases) {
      expect(carryRefusal(input), input).toEqual(expected);
    }
  });
});

describe('carry status classifiers and parsers (PHASE-60 S6)', () => {
  it('detects 404 and 409 responses cleanly', () => {
    expect(isCarryNotFound(new Error('/v1/conversations/c1/carry -> HTTP 404: Not Found'))).toBe(true);
    expect(isCarryNotFound(new Error('404'))).toBe(true);
    expect(isCarryNotFound(new Error('/v1/conversations/c1/carry -> HTTP 422: bad'))).toBe(false);

    expect(isCarryConflict(new Error('/v1/conversations/c1/carry -> HTTP 409: [object Object]'))).toBe(true);
    expect(isCarryConflict(new Error('HTTP 409'))).toBe(true);
    expect(isCarryConflict(new Error('/v1/conversations/c1/carry -> HTTP 404: Not Found'))).toBe(false);
  });

  it('parses optional cutoff turn input', () => {
    expect(parseCutoffTurn('')).toEqual({ ok: true, value: null });
    expect(parseCutoffTurn('   ')).toEqual({ ok: true, value: null });
    expect(parseCutoffTurn('0')).toEqual({ ok: true, value: 0 });
    expect(parseCutoffTurn(' 42 ')).toEqual({ ok: true, value: 42 });
    expect(parseCutoffTurn('-1')).toEqual({ ok: false });
    expect(parseCutoffTurn('3.5')).toEqual({ ok: false });
    expect(parseCutoffTurn('abc')).toEqual({ ok: false });
  });

  it('formats source labels, cutoff labels, and preview counts in both languages', () => {
    expect(carrySourceLabel({ id: '0190f3a4-1b2c', character: '세라', chat: '항구' })).toBe('세라 · 항구');
    expect(carrySourceLabel({ id: '0190f3a4-1b2c', character: '세라', chat: '세라' })).toBe('세라');
    expect(carrySourceLabel({ id: '0190f3a4-1b2c', character: null, chat: '항구' })).toBe('항구');
    expect(carrySourceLabel({ id: '0190f3a4-1b2c', character: null, chat: null })).toBe('0190f3a4');

    expect(carryCutoffLabel('ko', 18)).toBe('t18까지');
    expect(carryCutoffLabel('ko', null)).toBe('끝까지');
    expect(carryCutoffLabel('en', 18)).toBe('through t18');
    expect(carryCutoffLabel('en', null)).toBe('through the end');

    expect(carryCountsLine('ko', { facts: 12, aliases: 3, threads: 2, story: true }))
      .toBe('사실 12개 · 이름/별칭 3개 · 열린 약속 2개 · 지금까지의 이야기: 포함');
    expect(carryCountsLine('ko', { facts: 4, aliases: 0, threads: 1, story: false }))
      .toBe('사실 4개 · 이름/별칭 0개 · 열린 약속 1개 · 지금까지의 이야기: 포함 안 됨');
    expect(carryCountsLine('en', { facts: 12, aliases: 3, threads: 2, story: true }))
      .toBe('12 facts · 3 names/aliases · 2 open threads · story so far: included');
    expect(carryCountsLine('en', { facts: 4, aliases: 0, threads: 1, story: false }))
      .toBe('4 facts · 0 names/aliases · 1 open threads · story so far: not included');
  });
});

describe('carryErrorText (PHASE-60 S6)', () => {
  it('formats the size-limit 422 as a plain sentence in both languages with no status code', () => {
    const detail = 'too_many_rows: rows=2400 max=2000 (the reading holds 2400 rows; a link carries at most 2000)';
    const err = new Error(`/v1/conversations/c1/carry/preview -> HTTP 422: ${detail}`);
    const ko = carryErrorText('ko', err, uiErrorText);
    const en = carryErrorText('en', err, uiErrorText);
    expect(ko).toBe('이 채팅의 기억이 너무 많아 이어받을 수 없습니다 (2400줄, 최대 2000줄). 더 이른 턴에서 끊어 보세요.');
    expect(en).toBe('This chat has too much memory to carry (2400 lines, maximum 2000). Try cutting off at an earlier turn.');
    expect(ko).not.toMatch(/\b422\b|HTTP|too_many_rows/);
    expect(en).not.toMatch(/\b422\b|HTTP|too_many_rows/);
  });

  it("reads the sidecar's row-cap answer as the adapter hands it to the panel", async () => {
    // The sidecar's own wording: `TooManyRows` in carry.py is the sentence, `carry_refused` in api.py puts the marker
    // before it, and the 422 body carries the result as a plain string `detail`.
    const sentence = (rows: number, max: number) => `the reading holds ${rows} rows; a link carries at most ${max}`;
    const detail = (rows: number, max: number) => `too_many_rows: rows=${rows} max=${max} (${sentence(rows, max)})`;
    const host: HostPort = {
      settings: async () => ({ sidecarUrl: 'http://sidecar', authToken: '', enabled: true, reservedMemoryTokens: 600,
        deadlineMs: 200, injectPosition: 'before_last_user', route: 'direct', language: 'ko' }),
      currentChat: async () => null,
      request: async () => ({ status: 422, json: { detail: detail(2005, 2000) } }),
      warn: () => {},
      debug: () => {},
      now: () => performance.now(),
    };
    const adapter = createAdapter(host);
    const target = '0190f3a4-1b2c-7d3e-8f4a-5b6c7d8e9f01';
    for (const path of [`/v1/conversations/${target}/carry/preview`, `/v1/conversations/${target}/carry`]) {
      const error: unknown = await adapter.api('POST', path, { source_conversation_id: 's', mode: 'continue' })
        .then(() => null, (e: unknown) => e);
      expect((error as Error).message).toBe(`${path} -> HTTP 422: ${detail(2005, 2000)}`);
      expect(carryRefusal((error as Error).message)).toEqual({ rows: 2005, max: 2000 });
      expect(carryErrorText('en', error, uiErrorText))
        .toBe('This chat has too much memory to carry (2005 lines, maximum 2000). Try cutting off at an earlier turn.');
      expect(carryErrorText('ko', error, uiErrorText))
        .toBe('이 채팅의 기억이 너무 많아 이어받을 수 없습니다 (2005줄, 최대 2000줄). 더 이른 턴에서 끊어 보세요.');
    }
  });

  it('shows the sentence without the marker as any other refused input, not as the size limit', () => {
    const err = new Error('/v1/conversations/c1/carry/preview -> HTTP 422: the reading holds 2400 rows; a link carries at most 2000');
    expect(carryErrorText('en', err, uiErrorText)).toBe('Invalid: the reading holds 2400 rows; a link carries at most 2000');
  });

  it('shows other 422 details through errorText with no status code', () => {
    const err = new Error("/v1/conversations/c1/carry/preview -> HTTP 422: turn 99 is not on the source's current head");
    expect(carryErrorText('ko', err, uiErrorText)).toBe("입력 오류: turn 99 is not on the source's current head");
    expect(carryErrorText('en', err, uiErrorText)).toBe("Invalid: turn 99 is not on the source's current head");
  });

  it('never shows a bare HTTP status code for 404 or 5xx failures', () => {
    const noLink = new Error('/v1/conversations/c1/carry -> HTTP 404: no link in force');
    expect(carryErrorText('ko', noLink, uiErrorText)).toBe('현재 연결된 이전 채팅이 없습니다.');
    expect(carryErrorText('en', noLink, uiErrorText)).toBe('There is no link in force.');

    const missing = new Error('/v1/conversations/c1/carry -> HTTP 404: no conversation abc');
    expect(carryErrorText('ko', missing, uiErrorText)).toBe('해당 채팅을 찾을 수 없습니다.');
    expect(carryErrorText('en', missing, uiErrorText)).toBe('That chat could not be found.');

    const bare503 = new Error('/v1/conversations/c1/carry -> HTTP 503');
    expect(carryErrorText('ko', bare503, uiErrorText)).not.toMatch(/\b503\b|HTTP/);
    expect(carryErrorText('en', bare503, uiErrorText)).not.toMatch(/\b503\b|HTTP/);

    const detail500 = new Error('/v1/conversations/c1/carry -> HTTP 500: storage busy');
    expect(carryErrorText('ko', detail500, uiErrorText)).toBe('사이드카 오류: storage busy');
    expect(carryErrorText('en', detail500, uiErrorText)).toBe('Sidecar error: storage busy');
  });
});
