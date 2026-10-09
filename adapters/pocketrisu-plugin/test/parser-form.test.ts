import { describe, expect, it } from 'vitest';
import { parserDraft, parserBindings, presetRules } from '../src/parser-form';

describe('status drafts (PHASE-39 amendment 2)', () => {
  it('distinguishes a blank draft from an explicit empty rules document', () => {
    expect(parserDraft('  ')).toEqual({ ok: false, error: 'blank' });
    expect(parserDraft('{"rules":[]}')).toEqual({ ok: true, rules: [] });
  });
  it('accepts only a document containing rule objects and never compiles Python patterns in JS', () => {
    for (const text of ['[]', 'null', '{}', '{"rules":[null]}', '{"rules":[[]]}']) {
      expect(parserDraft(text)).toEqual({ ok: false, error: 'shape' });
    }
    expect(parserDraft('{')).toEqual({ ok: false, error: 'json' });
    const rules = [{ kind: 'regex', pattern: '(?P<value>\\d+)', card: 'Other' }];
    expect(parserDraft(JSON.stringify({ rules }))).toEqual({ ok: true, rules });
  });
  it('summarizes bound names separately from legacy unbound rules', () => {
    expect(parserBindings({ rules: [{ card: 'A' }, { card: 'B' }, { card: 'A' }, {}] }))
      .toEqual({ cards: [{ name: 'A', count: 2 }, { name: 'B', count: 1 }], unbound: 1 });
  });
  it('makes templates without carrying another card binding or mutating their source', () => {
    const original = [{ id: 'hp', card: 'A', key: 'HP', kind: 'regex' }];
    expect(presetRules(original)).toEqual([{ id: 'hp', key: 'HP', kind: 'regex' }]);
    expect(original[0]!.card).toBe('A');
  });
});
