// NMOS's note in the author's note (PHASE-50): never canon, and copied from the panel. The sidecar's
// `noteblocks.strip_blocks` is the same (fixtures/unit/note-blocks-v1.json).

// `[NMOS note · t<turn> · <date>]` … `[/NMOS note]`
const BLOCK = /\[NMOS note(?: · t(\d+))?(?: · [^\]\n]*)?\]\n?[\s\S]*?\[\/NMOS note\]\n?/g;

export interface NoteBlock { turn: string }

/** The note without NMOS's blocks, and the turn each was made at. A note without one comes back exactly as it was;
 *  an unclosed marker is not a block. */
export function stripNoteBlocks(text: string): { text: string; blocks: NoteBlock[] } {
  const blocks = [...text.matchAll(BLOCK)].map((m) => ({ turn: m[1] ?? '' }));
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
