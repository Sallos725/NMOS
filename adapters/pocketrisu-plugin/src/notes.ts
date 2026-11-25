// NMOS's note in the author's note (PHASE-50): never canon, and copied from the panel. The sidecar's
// `noteblocks.strip_blocks` is the same (fixtures/unit/note-blocks-v1.json).

// `[NMOS note · t<turn> · <date>]` … `[/NMOS note]`
const BLOCK = /\[NMOS note(?: · t(\d+))?(?: · [^\]\n]*)?\]\n?[\s\S]*?\[\/NMOS note\]\n?/g;

export interface NoteBlock { turn: string }

/** Characters of the owner's prompt for the custom part (PHASE-56 C1), as the sidecar's `notes.PROMPT_MAX`. */
export const PROMPT_MAX = 4000;

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

/** Split a generated note (`[NMOS note ...] ... [/NMOS note]`) into `## Heading` sections for per-section copying. */
export function splitNoteSections(text: string): { title: string; body: string }[] {
  const inner = text.trim()
    .replace(/^\[NMOS note[^\]]*\]\n?/, '')
    .replace(/\n?\[\/NMOS note\]\s*$/, '')
    .trim();
  if (!inner) return [];
  const parts = inner.split(/(?=^## )/m).map((s) => s.trim()).filter(Boolean);
  const out: { title: string; body: string }[] = [];
  for (const part of parts) {
    const nl = part.indexOf('\n');
    if (part.startsWith('## ')) {
      const title = (nl === -1 ? part : part.slice(0, nl)).slice(3).trim();
      out.push({ title: title || 'Section', body: part });
    } else if (out.length) {
      out[out.length - 1]!.body += `\n\n${part}`;
    } else {
      out.push({ title: 'Note', body: part });
    }
  }
  return out;
}

export interface NotePreset { name: string; prompt: string }

const PRESETS_KEY = 'nmos_note_presets_v1';
const MAX_CUSTOM_PRESETS = 6;

/** Read user-saved custom note prompt presets from storage (best-effort in sandboxed frames). */
export function loadNotePresets(storage?: Pick<Storage, 'getItem'> | null): NotePreset[] {
  try {
    const raw = (storage ?? globalThis.localStorage)?.getItem(PRESETS_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((x): x is NotePreset => !!x && typeof x.name === 'string' && typeof x.prompt === 'string'
        && x.name.trim().length > 0 && x.prompt.trim().length > 0)
      .slice(0, MAX_CUSTOM_PRESETS)
      .map((x) => ({ name: x.name.trim().slice(0, 40), prompt: x.prompt.trim().slice(0, PROMPT_MAX) }));
  } catch {
    return [];
  }
}

/** Persist user-saved custom note prompt presets (best-effort). */
export function saveNotePresets(presets: NotePreset[], storage?: Pick<Storage, 'setItem'> | null): void {
  try {
    (storage ?? globalThis.localStorage)?.setItem(PRESETS_KEY, JSON.stringify(presets.slice(0, MAX_CUSTOM_PRESETS)));
  } catch { /* storage blocked in sandbox */ }
}
