import { describe, expect, it } from 'vitest';
import { inspectorApiPath, inspectorConversation, keepAttribute, localTime, sectionTarget } from '../src/inspector';

const id = '0190f3a4-1b2c-7d3e-8f40-123456789abc';
const who = '5c6d7e8f-9a0b-5c2d-8e3f-0123456789ab';

describe('inspector links', () => {
  it('map the sidecar inspector pages to their panel API and nothing else', () => {
    expect(inspectorApiPath('/inspector')).toBe('/v1/inspector');
    expect(inspectorApiPath('/inspector?lang=en')).toBe('/v1/inspector');
    expect(inspectorApiPath(`/inspector/c/${id}`)).toBe(`/v1/inspector/c/${id}`);
    expect(inspectorApiPath(`/inspector/c/${id}?token=x&lang=en`)).toBe(`/v1/inspector/c/${id}`);
    expect(inspectorApiPath(`/inspector/c/${id}/e/${who}?lang=en`)).toBe(`/v1/inspector/c/${id}/e/${who}`);
    for (const href of [null, '', 'https://example.com/inspector', 'javascript:alert(1)', '/inspector/c/../../v1/config',
      '/inspectorx', `/inspector/c/${id}/x`, '//evil/inspector', `/inspector/c/${id}/e/x`, `/inspector/e/${who}`,
      `/inspector/c/${id}/e/${who}/x`]) {
      expect(inspectorApiPath(href), String(href)).toBeNull();
    }
  });
});

describe('inspectorConversation', () => {
  it('finds the conversation of a conversation or character page only', () => {
    const conv = '0199a3b2-1c2d-7e3f-8a4b-5c6d7e8f9a0b';
    expect(inspectorConversation(`/v1/inspector/c/${conv}`)).toBe(conv);
    expect(inspectorConversation(`/v1/inspector/c/${conv}/e/${who}`)).toBe(conv);
    expect(inspectorConversation('/v1/inspector')).toBeNull();
    expect(inspectorConversation(`/v1/inspector/c/${conv}/x`)).toBeNull();
    expect(inspectorConversation('/v1/inspector/c/not-a-uuid')).toBeNull();
  });
});

describe('inspector markup', () => {
  it('keeps section anchors and folds, and nothing that could run or load', () => {
    expect(sectionTarget('#s-facts')).toBe('s-facts');
    for (const href of [null, '', 's-facts', '#facts', '#s-FACTS', '#s-facts"x', '#s-a-b', '/inspector#s-facts']) {
      expect(sectionTarget(href), String(href)).toBeNull();
    }
    expect(keepAttribute('id', 's-conflicts')).toBe(true);
    expect(keepAttribute('id', 'nmos-panel')).toBe(false); // the panel's own ids are not for the page
    expect(keepAttribute('open', '')).toBe(true);
    expect(keepAttribute('href', '#s-held')).toBe(true);
    expect(keepAttribute('href', `/inspector/c/${id}/e/${who}`)).toBe(true);
    for (const [name, value] of [['href', 'javascript:alert(1)'], ['href', '#top'], ['onclick', 'x()'], ['style', 'x'],
      ['onerror', 'x'], ['src', 'x']] as const) {
      expect(keepAttribute(name, value), name).toBe(false);
    }
  });
});

describe('localTime', () => {
  const now = new Date('2026-09-24T12:00:00Z');
  it('is relative within a week and a local date after that', () => {
    expect(localTime('2026-09-24T11:59:50+00:00', 'en', now)?.text).toBe('now');
    expect(localTime('2026-09-24T11:57:00+00:00', 'en', now)?.text).toBe('3 minutes ago');
    expect(localTime('2026-09-24T09:00:00+00:00', 'en', now)?.text).toBe('3 hours ago');
    expect(localTime('2026-09-22T12:00:00+00:00', 'ko', now)?.text).toBe('그저께');
    expect(localTime('2026-09-01T12:00:00+00:00', 'en', now)?.text).toMatch(/2026/);
    expect(localTime('2026-09-24T12:30:00+00:00', 'en', now)?.text).toMatch(/2026/); // a clock ahead of ours
    expect(localTime('not a time', 'ko', now)).toBeNull();
  });
});
