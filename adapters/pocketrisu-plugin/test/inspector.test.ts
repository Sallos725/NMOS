import { describe, expect, it } from 'vitest';
import { closeOutcomes, entityNamed, inspectorApiPath, inspectorConversation, inspectorEntity, keepAttribute, linkChoices,
  localTime, previewText, repairAction, sectionTarget, splitChoices } from '../src/inspector';
import type { EntityRow, Preview } from '../src/inspector';
import { t, type StringKey } from '../src/i18n';

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

describe('repair marks (ADR 0044)', () => {
  it('parse a kind, an item and a character or field, and nothing else', () => {
    expect(repairAction(`thread_close:${id}`)).toEqual({ kind: 'thread_close', item: id, extra: null });
    expect(repairAction(`secret_found_out:-3:${encodeURIComponent('하나')}`)).toEqual(
      { kind: 'secret_found_out', item: '-3', extra: '하나' });
    // the sidecar percent-encodes a name, so any text is data (Codex review of step 5)
    expect(repairAction('secret_keep:3:O%27Neil%20%26%20Co%3A%201')?.extra).toBe("O'Neil & Co: 1");
    expect(repairAction('fact_correct:42:object')).toEqual({ kind: 'fact_correct', item: '42', extra: 'object' });
    expect(repairAction('fact_lock:42')).toEqual({ kind: 'fact_lock', item: '42', extra: null });  // ADR 0047
    expect(repairAction('fact_restore:42')).toEqual({ kind: 'fact_restore', item: '42', extra: null });  // PHASE-22 Q7
    // PHASE-26: the repair to move, and the item it may now mean
    expect(repairAction(`repair_move:${id}:${encodeURIComponent('3f1a-c')}`)).toEqual(
      { kind: 'repair_move', item: id, extra: '3f1a-c' });
    expect(repairAction(`undo:${who}`)?.kind).toBe('undo');
    for (const value of [null, '', 'thread_close', 'thread_close:', 'name_split:1:x', 'drop:1', 'thread_close:xyz',
      'thread_close:1:a:b', 'secret_keep:1:<b>', 'secret_keep:1:"x"', 'THREAD_CLOSE:1', ` thread_close:1`,
      'secret_keep:1:하나', 'secret_keep:1:%E0%A4%A', 'secret_keep:1:%00x', 'secret_keep:1:%20',
      `thread_close:${'1'.repeat(65)}`, `secret_keep:1:${'가'.repeat(121)}`]) {
      expect(repairAction(value), String(value)).toBeNull();
    }
    expect(closeOutcomes(repairAction('thread_close:7:kept,broken')?.extra ?? null)).toEqual(['kept', 'broken']);
    expect(closeOutcomes('achieved,Bad,x y,')).toEqual(['achieved']);
    expect(closeOutcomes(null)).toEqual([]);
    expect(keepAttribute('data-repair', 'thread_reopen:7')).toBe(true);
    expect(keepAttribute('data-repair', 'javascript:alert(1)')).toBe(false);
    expect(keepAttribute('data-other', 'thread_reopen:7')).toBe(false);
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

describe('owner links on an entity page (ADR 0025)', () => {
  const conv = '0199a3b2-1c2d-7e3f-8a4b-5c6d7e8f9a0b';
  const row = (id: string, name: string, mentions: number, type = 'character', extra: Partial<EntityRow> = {}): EntityRow =>
    ({ id, type, name, names: [name], mentions, links: [], ...extra });

  it('finds the entity of a character page only', () => {
    expect(inspectorEntity(`/v1/inspector/c/${conv}/e/${who}`)).toEqual({ conversation: conv, entity: who });
    expect(inspectorEntity(`/v1/inspector/c/${conv}`)).toBeNull();
    expect(inspectorEntity(`/v1/inspector/c/${conv}/e/x`)).toBeNull();
  });

  it('offers the other entities of the same type, most mentioned first', () => {
    const fox = row('a', '?붉은 여우 꼬리의 여자', 2);
    const entities = [fox, row('b', '노엘', 40), row('c', '아델라', 25), row('d', '관측실', 9, 'place')];
    const choices = linkChoices(entities, 'a');
    expect(choices?.self).toBe(fox);
    expect(choices?.others.map((e) => e.name)).toEqual(['노엘', '아델라']);
    expect(linkChoices(entities, 'zz')).toBeNull(); // the entity is gone
    expect(linkChoices(entities.map(({ links, ...e }) => e), 'a')).toBeNull(); // an older sidecar: no owner links
  });

  it('follows a name to the entity that holds it after a join or an undo', () => {
    const joined = [row('c', '아델라', 27, 'character', { names: ['아델라', '?붉은 여우 꼬리의 여자'] })];
    expect(entityNamed(joined, 'character', '?붉은 여우 꼬리의 여자')?.id).toBe('c');
    expect(entityNamed(joined, 'item', '아델라')).toBeNull();
  });

  it('offers a split for each pair of story aliases that still joins names of this entity (K8)', () => {
    const hana = row('a', '하나', 30, 'character', { names: ['하나', '하나 씨', '유이'], aliases: [
      { name: '하나', other: '하나 씨', turn: 2 }, { name: '하나 씨', other: '하나', turn: 5 }, // one pair, twice
      { name: '하나', other: '유이', turn: 7 },
      { name: '하나', other: '카이토', turn: 9 }, // refused by resolution: not one entity
    ] });
    expect(splitChoices(hana)).toEqual([{ name: '하나', other: '하나 씨' }, { name: '하나', other: '유이' }]);
    expect(splitChoices(row('b', '카이토', 3))).toEqual([]); // an older sidecar: no aliases
  });
});

describe('join preview (PHASE-20)', () => {
  const en = (key: StringKey, vars?: Record<string, string | number>) => t('en', key, vars);
  const entity = (name: string, names = [name], persona = false) => ({ id: name, name, names, persona });
  const base: Preview = { action: 'join', changes: true, before: [entity('Rin'), entity('Mina')],
    after: [entity('Mina', ['Mina', 'Rin'])], lines: [], counts: {}, fingerprint: 'f' };

  it('says nothing changes when nothing does', () => {
    expect(previewText({ ...base, changes: false }, en)).toEqual([en('pv.nothing')]);
  });

  it("names no entity for a repair's move (PHASE-26)", () => {
    const move = { ...base, before: [], after: [] };
    expect(previewText({ ...move, changes: false }, en)).toEqual([en('pv.nothing_memory')]);
    const lines: Preview['lines'] = [
      { kind: 'thread_status', thread: { text: 'find the key', by: 'Hana', turn: 7 }, status: 'achieved' }];
    const out = previewText({ ...move, changes: true, lines }, en);
    expect(out).toHaveLength(1);  // the change alone, no entity line
    expect(out[0]).toContain('find the key');
  });

  it('puts the entities first and the warnings before the rest, with how many more', () => {
    const lines: Preview['lines'] = [
      { kind: 'secret', secret: { text: 'who holds the key', turn: 1 } },  // an ordinary secret line first
      { kind: 'fact_merged', fact: { text: 'Mina identity knight', turn: 3 }, by: { text: 'Rin identity knight' } },
      { kind: 'fact_replaced', fact: { text: 'Mina located in chapel' }, by: { text: 'Rin located in harbor', turn: 2 } },
      { kind: 'self_thread', thread: { text: 'wait', by: 'Mina', turn: 5 } },
      { kind: 'secret', secret: { text: 'the letter is forged', turn: 4 }, kept_from_holder: true },
      { kind: 'repair', repair: { kind: 'fact_retract' }, before: '1', after: null },
      { kind: 'something_new' },
    ];
    const out = previewText({ ...base, lines }, en, (s) => s, 3);
    expect(out.slice(0, 3)).toEqual(['Rin, Mina → Mina', '"Mina" also goes by: Rin',
      '"Mina"\'s Inspector page stays; the other one goes']);
    expect(out.slice(3, 6)).toEqual([  // the warnings first, whatever their kind, each with its turn (Q1)
      "Note: Mina's promise \"wait\" becomes one to themselves (turn 5)",
      'Note: the secret "the letter is forged" is kept from someone who holds it (turn 4)',
      'Who holds or is kept from the secret "who holds the key" changes (turn 1)',  // then the kinds' order
    ]);
    expect(out[6]).toBe(en('pv.more', { n: 4 })); // three worded lines left, and the kind this panel does not know
  });

  it('words every mirror kind of an undo', () => {
    const kinds = ['fact_back', 'self_relation_gone', 'self_thread_gone', 'thread_back', 'secret_back', 'conflict_gone',
      'persona_gone', 'canon_alias_gone', 'thread_status', 'thread_merged', 'secret_merged', 'fact_ended',
      'conflict_new', 'persona', 'canon_alias', 'self_relation'];
    const lines = kinds.map((kind) => ({ kind, fact: { text: 'x' }, thread: { text: 'x', by: 'A' }, secret: { text: 'x' },
      conflict: { text: 'x' }, name: 'A', other: 'B', status: 'kept' }));
    const out = previewText({ ...base, lines }, en, (s) => s, 99);
    expect(out).toHaveLength(kinds.length + 3); // the entities, the other name, the page that stays
    expect(out.every((x) => x && !x.includes('{'))).toBe(true);
  });

  it('parses the undo mark of a name split', () => {
    expect(repairAction(`undo:${id}:name_split`)).toEqual({ kind: 'undo', item: id, extra: 'name_split' });
  });
});
