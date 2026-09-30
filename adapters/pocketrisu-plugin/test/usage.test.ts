import { describe, expect, it } from 'vitest';
import { usageText } from '../src/usage';

const total = { calls: 12, reported: 12, input: 48210, output: 3105, cached: 20480 };

describe('usageText (PHASE-17 Q4)', () => {
  it('says calls and reported tokens, cached input when there is some', () => {
    expect(usageText(total, 'ko')).toBe('NMOS 모델 사용: 호출 12회 · 입력 48,210 · 출력 3,105 토큰 (입력 중 캐시 20,480)');
    expect(usageText({ ...total, cached: 0 }, 'en')).toBe('NMOS model use: 12 calls · 48,210 input · 3,105 output tokens');
  });
  it('says when only some calls were reported', () => {
    expect(usageText({ ...total, reported: 5, cached: 0 }, 'en'))
      .toBe('NMOS model use: 12 calls · 48,210 input · 3,105 output tokens · 5 of 12 calls reported');
  });
  it('never shows zero tokens for a provider that reported nothing', () => {
    expect(usageText({ calls: 3, reported: 0, input: 0, output: 0, cached: 0 }, 'ko'))
      .toBe('NMOS 모델 사용: 호출 3회 (제공자가 토큰을 보고하지 않음)');
  });
  it('tells memory an older version made, whose usage was not recorded, from memory with no model work', () => {
    const none = { calls: 0, reported: 0, input: 0, output: 0, cached: 0 };
    expect(usageText({ ...none, not_recorded: 40 }, 'en')).toBe('NMOS model use: not recorded (this memory was made by an older version)');
    expect(usageText({ ...total, cached: 0, not_recorded: 40 }, 'en'))
      .toBe('NMOS model use: 12 calls · 48,210 input · 3,105 output tokens · 40 results from an older version not recorded');
  });
  it('leaves out output tokens no call reported, rather than show 0', () => {
    expect(usageText({ calls: 30, reported: 30, input: 900, output: 0, cached: 0, output_reported: 0 }, 'ko'))
      .toBe('NMOS 모델 사용: 호출 30회 · 입력 900 토큰');
  });
  it('leaves out input tokens no call reported (a provider that gives only output)', () => {
    expect(usageText({ calls: 2, reported: 2, input: 0, output: 50, cached: 0, input_reported: 0, output_reported: 2 }, 'en'))
      .toBe('NMOS model use: 2 calls · 50 output tokens');
  });
  it('says cached tokens a provider reported without input or output (Copilot re-review)', () => {
    expect(usageText({ calls: 1, reported: 1, input: 0, output: 0, cached: 31, input_reported: 0, output_reported: 0 }, 'en'))
      .toBe('NMOS model use: 1 calls · 31 cached input tokens');
    expect(usageText({ calls: 1, reported: 1, input: 0, output: 0, cached: 0, input_reported: 0, output_reported: 0 }, 'ko'))
      .toBe('NMOS 모델 사용: 호출 1회');
  });
  it('says nothing was recorded yet', () => {
    expect(usageText({ calls: 0, reported: 0, input: 0, output: 0, cached: 0 }, 'en')).toBe('NMOS model use: none recorded yet');
  });
});
