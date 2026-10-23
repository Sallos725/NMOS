// @vitest-environment happy-dom
// PHASE-50: NMOS's sections in the author's note — never canon, and copied from the panel.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { copyText, stripNoteBlocks } from '../src/notes';
import { canonTexts } from '../src/canon';
import type { HostChat } from '../src/types';

// happy-dom's import.meta.url is not a file URL: the tests run from the plugin's folder (npm test)
const doc = JSON.parse(readFileSync(resolve(process.cwd(), '../../fixtures/unit/note-blocks-v1.json'), 'utf8'));

describe('NMOS note blocks (PHASE-50 S5)', () => {
  it('are removed as the sidecar removes them (fixtures/unit/note-blocks-v1.json)', () => {
    for (const c of doc.cases) expect(stripNoteBlocks(c.note), c.name).toEqual({ text: c.text, blocks: c.blocks });
  });

  it('leave the note in canon without them, named in its metadata; a note without one is unchanged', () => {
    const chat: HostChat = { id: 'c', note: doc.cases[1].note, message: [] };
    const note = canonTexts(null, chat, [], null).find((t) => t.key === 'note')!;
    expect(note.text).toBe('지금은 한겨울 밤이다.');
    expect(note.metadata).toEqual({ nmos_blocks: [{ kind: 'chronicle', turns: '0-87' }] });
    const plain = canonTexts(null, { ...chat, note: '  그냥 메모\n' }, [], null).find((t) => t.key === 'note')!;
    expect(plain).toEqual({ key: 'note', text: '  그냥 메모\n', metadata: {} });
    expect(canonTexts(null, { ...chat, note: doc.cases[4].note }, [], null).find((t) => t.key === 'note')).toBeUndefined();
  });
});

describe('copying a section (PHASE-50 S6)', () => {
  it('copies, and selects the text where the clipboard is refused', async () => {
    const box = document.createElement('textarea');
    box.value = '[NMOS 연대기 · t0–1 · 2026-10-23]\n- a\n[/NMOS 연대기]';
    document.body.append(box);
    let copied = '';
    expect(await copyText(box, { writeText: async (t: string) => { copied = t; } })).toBe(true);
    expect(copied).toBe(box.value);
    expect(await copyText(box, { writeText: async () => { throw new Error('denied'); } })).toBe(false);
    expect(await copyText(box, undefined)).toBe(false);
    expect(box.selectionEnd - box.selectionStart).toBe(box.value.length);
  });
});
