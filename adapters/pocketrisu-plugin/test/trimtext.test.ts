import { describe, expect, it } from 'vitest';
import { trimHudSuffix, trimReason, trimStatusLine, type TrimShown } from '../src/trimtext';

const KNOWN_REASONS: [string, string, string][] = [
  ['format', '프리셋이 대화를 메시지별로 보내지 않아 안전하게 뺄 수 없음', 'the preset does not send the chat one message at a time'],
  ['short', '아직 뺄 만큼 길지 않음', 'the chat is not long enough yet'],
  ['uncovered', '기억 정리(추출·요약)가 아직 따라오지 못함', 'memory (extraction and summaries) has not caught up yet'],
  ['no_summaries', '요약이 꺼져 있음 (요약이 필요합니다)', 'summaries are off (trimming needs them)'],
  ['stale', '기억이 이 채팅의 최신 상태가 아님', "memory is not at the chat's latest state"],
  ['empty_packet', '이번에 넣을 기억이 없음', 'no memory for this request'],
  ['failed', 'NMOS의 답을 받지 못함', 'no answer from NMOS'],
  ['unsupported', 'NMOS가 이 기능을 지원하지 않음 (업데이트 필요)', 'NMOS does not support it yet (update it)'],
];

describe('trimReason (PHASE-60 S1)', () => {
  it('returns an empty string for null', () => {
    expect(trimReason('ko', null)).toBe('');
    expect(trimReason('en', null)).toBe('');
  });

  it('formats every known reason in both languages', () => {
    for (const [reason, ko, en] of KNOWN_REASONS) {
      expect(trimReason('ko', reason), `ko:${reason}`).toBe(ko);
      expect(trimReason('en', reason), `en:${reason}`).toBe(en);
    }
  });

  it('falls back to other for an unknown reason from a newer sidecar', () => {
    expect(trimReason('ko', 'future_gate')).toBe('기타 (future_gate)');
    expect(trimReason('en', 'future_gate')).toBe('other (future_gate)');
    expect(trimReason('en', 'toString')).toBe('other (toString)');
  });
});

describe('trimStatusLine (PHASE-60 S1)', () => {
  it('returns null when trim is absent or has nothing to report', () => {
    expect(trimStatusLine('ko', null)).toBeNull();
    expect(trimStatusLine('en', undefined)).toBeNull();
    expect(trimStatusLine('ko', { dropped: 0, savedTokens: 0, reason: null })).toBeNull();
    expect(trimStatusLine('en', { dropped: 0, savedTokens: 0, reason: null })).toBeNull();
  });

  it('reports dropped messages and formatted saved tokens with thousands separators', () => {
    const shown: TrimShown = { dropped: 12, savedTokens: 1234, reason: null };
    expect(trimStatusLine('ko', shown)).toBe('오래된 대화 12개를 빼고 보냈습니다 (약 1,234토큰 절약)');
    expect(trimStatusLine('en', shown)).toBe('Left out 12 old messages (about 1,234 tokens saved)');
  });

  it('prefers the dropped count when dropped > 0 even if a reason is also present', () => {
    const shown: TrimShown = { dropped: 4, savedTokens: 500, reason: 'short' };
    expect(trimStatusLine('ko', shown)).toBe('오래된 대화 4개를 빼고 보냈습니다 (약 500토큰 절약)');
    expect(trimStatusLine('en', shown)).toBe('Left out 4 old messages (about 500 tokens saved)');
  });

  it('reports why nothing was left out when dropped is 0 and reason is set', () => {
    expect(trimStatusLine('ko', { dropped: 0, savedTokens: 0, reason: 'no_summaries' }))
      .toBe('오래된 대화를 빼지 않았습니다: 요약이 꺼져 있음 (요약이 필요합니다)');
    expect(trimStatusLine('en', { dropped: 0, savedTokens: 0, reason: 'no_summaries' }))
      .toBe('No old messages left out: summaries are off (trimming needs them)');
    expect(trimStatusLine('ko', { dropped: 0, savedTokens: 0, reason: 'custom_stop' }))
      .toBe('오래된 대화를 빼지 않았습니다: 기타 (custom_stop)');
    expect(trimStatusLine('en', { dropped: 0, savedTokens: 0, reason: 'custom_stop' }))
      .toBe('No old messages left out: other (custom_stop)');
  });
});

describe('trimHudSuffix (PHASE-60 S1)', () => {
  it('returns an empty string when trim is absent or has nothing to report', () => {
    expect(trimHudSuffix('ko', null)).toBe('');
    expect(trimHudSuffix('en', undefined)).toBe('');
    expect(trimHudSuffix('ko', { dropped: 0, savedTokens: 0, reason: null })).toBe('');
    expect(trimHudSuffix('en', { dropped: 0, savedTokens: 0, reason: null })).toBe('');
  });

  it('returns the dropped suffix when messages were left out', () => {
    const shown: TrimShown = { dropped: 12, savedTokens: 3400, reason: null };
    expect(trimHudSuffix('ko', shown)).toBe(' · 오래된 대화 12개 뺌 (약 3,400토큰)');
    expect(trimHudSuffix('en', shown)).toBe(' · 12 old messages left out (~3,400 tokens)');
  });

  it('returns the kept suffix with the translated reason when nothing was dropped', () => {
    expect(trimHudSuffix('ko', { dropped: 0, savedTokens: 0, reason: 'uncovered' }))
      .toBe(' · 대화 그대로: 기억 정리(추출·요약)가 아직 따라오지 못함');
    expect(trimHudSuffix('en', { dropped: 0, savedTokens: 0, reason: 'uncovered' }))
      .toBe(' · dialogue kept: memory (extraction and summaries) has not caught up yet');
    expect(trimHudSuffix('ko', { dropped: 0, savedTokens: 0, reason: 'new_code' }))
      .toBe(' · 대화 그대로: 기타 (new_code)');
    expect(trimHudSuffix('en', { dropped: 0, savedTokens: 0, reason: 'new_code' }))
      .toBe(' · dialogue kept: other (new_code)');
  });
});
