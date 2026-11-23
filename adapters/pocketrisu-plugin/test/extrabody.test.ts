import { describe, expect, it } from 'vitest';
import { bodyKey, bodyOf, EFFORTS, effortOf, isOpenRouter, showBody, withEffort } from '../src/extrabody';

describe('extra request values (PHASE-61 S4, A7)', () => {
  it('reads the effort from a text', () => {
    expect(effortOf('')).toEqual({ state: 'none' });
    expect(effortOf('  \n ')).toEqual({ state: 'none' });
    expect(effortOf('{}')).toEqual({ state: 'none' });
    expect(effortOf('{"max_tokens": 900}')).toEqual({ state: 'none' });
    expect(effortOf('{"reasoning": {"exclude": true}}')).toEqual({ state: 'none' });
    for (const e of EFFORTS) expect(effortOf(JSON.stringify({ reasoning: { effort: e } }))).toEqual({ state: 'value', effort: e });
    expect(effortOf('{"reasoning": {"effort": "turbo"}}')).toEqual({ state: 'custom' });
    expect(effortOf('{"reasoning": {"effort": 3}}')).toEqual({ state: 'custom' });
    expect(effortOf('{"reasoning": "low"}')).toEqual({ state: 'custom' });
    expect(effortOf('{"reasoning": ["low"]}')).toEqual({ state: 'custom' });
    expect(effortOf('{"reasoning": null}')).toEqual({ state: 'custom' });
    for (const bad of ['{', '[]', 'null', '"low"', '3', '{"a": 1,}']) expect(effortOf(bad), bad).toEqual({ state: 'invalid' });
  });

  it('the values are the seven of Q3', () => {
    expect([...EFFORTS]).toEqual(['none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max']);
  });

  it('writes the effort, keeping every other key in its order, and removes it again', () => {
    expect(withEffort('', 'low')).toBe('{\n  "reasoning": {\n    "effort": "low"\n  }\n}');
    const text = '{"provider": {"sort": "price"}, "reasoning": {"exclude": true}, "max_tokens": 900}';
    const set = withEffort(text, 'high');
    expect(JSON.parse(set)).toEqual({ provider: { sort: 'price' }, reasoning: { exclude: true, effort: 'high' }, max_tokens: 900 });
    expect(Object.keys(JSON.parse(set))).toEqual(['provider', 'reasoning', 'max_tokens']);
    expect(Object.keys(JSON.parse(set).reasoning)).toEqual(['exclude', 'effort']);
    expect(set).toBe(JSON.stringify(JSON.parse(set), null, 2));
    // changing it keeps its place
    const moved = withEffort('{"reasoning": {"effort": "low", "exclude": true}}', 'max');
    expect(Object.entries(JSON.parse(moved).reasoning)).toEqual([['effort', 'max'], ['exclude', true]]);
    // "—" removes effort, and reasoning when that leaves it empty
    expect(JSON.parse(withEffort(set, null))).toEqual({ provider: { sort: 'price' }, reasoning: { exclude: true }, max_tokens: 900 });
    expect(JSON.parse(withEffort('{"reasoning": {"effort": "low"}, "a": 1}', null))).toEqual({ a: 1 });
    // a reasoning that is not an object: replaced by a value, left alone by "—"
    expect(JSON.parse(withEffort('{"reasoning": "on"}', 'low'))).toEqual({ reasoning: { effort: 'low' } });
    expect(JSON.parse(withEffort('{"reasoning": "on"}', null))).toEqual({ reasoning: 'on' });
    // not a JSON object: unchanged
    for (const bad of ['{', '[1]', 'null']) {
      expect(withEffort(bad, 'low')).toBe(bad);
      expect(withEffort(bad, null)).toBe(bad);
    }
  });

  it('round-trips an empty body to what a fresh load shows', () => {
    expect(showBody({})).toBe('');
    expect(withEffort(withEffort(showBody({}), 'low'), null)).toBe(showBody({}));
    const loaded = showBody({ a: 1 });
    expect(withEffort(withEffort(loaded, 'medium'), null)).toBe(loaded);
    for (const e of EFFORTS) expect(effortOf(withEffort(loaded, e))).toEqual({ state: 'value', effort: e });
  });

  it('gives the object to send, or null for a text that is not one', () => {
    expect(bodyOf('')).toEqual({});
    expect(bodyOf(' {"a": [1, 2]} ')).toEqual({ a: [1, 2] });
    for (const bad of ['{', '[]', 'null', '"x"', '1']) expect(bodyOf(bad), bad).toBeNull();
  });

  it('compares bodies by their objects, not their text', () => {
    expect(bodyKey('')).toBe(bodyKey('{}'));
    expect(bodyKey('{"a": 1, "b": {"c": 2}}')).toBe(bodyKey('{\n  "b": {"c":2},\n  "a":1\n}'));
    expect(bodyKey('{"a": 1}')).not.toBe(bodyKey('{"a": 2}'));
    expect(bodyKey('{')).not.toBe(bodyKey('{}'));
    expect(bodyKey('{')).not.toBe(bodyKey('{ '));
  });

  it("recognises OpenRouter's address only", () => {
    for (const url of ['https://openrouter.ai/api/v1', ' https://OpenRouter.AI/api/v1 ', 'https://eu.openrouter.ai/api/v1',
      'http://openrouter.ai:443/v1']) expect(isOpenRouter(url), url).toBe(true);
    for (const url of ['', 'openrouter.ai/api/v1', 'not a url', 'https://notopenrouter.ai/v1',
      'https://openrouter.ai.example.com/v1', 'https://api.openai.com/v1', 'https://example.com/openrouter.ai'])
      expect(isOpenRouter(url), url).toBe(false);
  });
});
