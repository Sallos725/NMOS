// NMOS's sections in the author's note (PHASE-50): never canon, and copied from the panel. The sidecar's
// `noteblocks.strip_blocks` is the same (fixtures/unit/note-blocks-v1.json).

const LABELS: Record<string, string> = {
  '연대기': 'chronicle', chronicle: 'chronicle', '설정 변경점': 'changed', changed: 'changed',
  '호칭·관계': 'address', address: 'address',
};
const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const LABEL = Object.keys(LABELS).map(escape).join('|');
// `[NMOS <label> · t<first>[–<last>] · <date>]` … `[/NMOS <label>]`: the closing label is the opening one.
const BLOCK = new RegExp(`\\[NMOS (${LABEL})(?: · t(\\d+)(?:–(\\d+))?)?(?: · [^\\]\\n]*)?\\]\\n?[\\s\\S]*?\\[/NMOS \\1\\]\\n?`, 'g');

export interface NoteBlock { kind: string; turns: string }

/** The note without NMOS's sections, and each one's kind and turns ("0-87", "120"). A note without one comes back
 *  exactly as it was; an unclosed marker is not a section. */
export function stripNoteBlocks(text: string): { text: string; blocks: NoteBlock[] } {
  const blocks: NoteBlock[] = [];
  for (const m of text.matchAll(BLOCK)) {
    blocks.push({ kind: LABELS[m[1]!]!, turns: m[2] ? m[2] + (m[3] ? `-${m[3]}` : '') : '' });
  }
  if (!blocks.length) return { text, blocks };
  return { text: text.replace(BLOCK, '\n\n').replace(/\n{3,}/g, '\n\n').trim(), blocks };
}

/** Copy a box's text; where the frame refuses the clipboard (iPhone Safari), select it for the reader to copy. */
export async function copyText(box: HTMLTextAreaElement, clipboard: Pick<Clipboard, 'writeText'> | undefined):
  Promise<boolean> {
  try {
    if (!clipboard) throw new Error('no clipboard');
    await clipboard.writeText(box.value);
    return true;
  } catch {
    box.focus();
    box.select();
    box.setSelectionRange(0, box.value.length);
    return false;
  }
}
