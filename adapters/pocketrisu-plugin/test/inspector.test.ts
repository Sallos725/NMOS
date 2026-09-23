import { describe, expect, it } from 'vitest';
import { inspectorApiPath } from '../src/inspector';

describe('inspector links', () => {
  it('map the sidecar inspector pages to their panel API and nothing else', () => {
    const id = '0190f3a4-1b2c-7d3e-8f40-123456789abc';
    expect(inspectorApiPath('/inspector')).toBe('/v1/inspector');
    expect(inspectorApiPath('/inspector?lang=en')).toBe('/v1/inspector');
    expect(inspectorApiPath(`/inspector/c/${id}`)).toBe(`/v1/inspector/c/${id}`);
    expect(inspectorApiPath(`/inspector/c/${id}?token=x&lang=en`)).toBe(`/v1/inspector/c/${id}`);
    for (const href of [null, '', 'https://example.com/inspector', 'javascript:alert(1)', '/inspector/c/../../v1/config',
      '/inspectorx', `/inspector/c/${id}/x`, '//evil/inspector']) {
      expect(inspectorApiPath(href), String(href)).toBeNull();
    }
  });
});
