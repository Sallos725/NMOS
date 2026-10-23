"""Notes for the author's note (PHASE-50): sections the owner pastes into a chat's author's note, made on request.

Three kinds: the chronicle (the story's events, how they went and ended, from the scene summaries and the threads; one
model call, with an assembled fallback), what changed from the setting (canon values a story fact now supersedes) and
address and standing (each pair's relationship, role, feeling and form of address). Each is written between two marker
lines. The author's note is canon (ADR 0045), so the canon never reads a marked block: the plugin removes them before
the hash, and `canonfacts.process` again before a read (an older plugin sends them whole).

Nothing is stored and no packet reads these sections: they are views of memory, made when asked.
"""

from __future__ import annotations

import re
from typing import Any

KINDS = ("chronicle", "changed", "address")
LABELS = {"chronicle": ("연대기", "chronicle"), "changed": ("설정 변경점", "changed"), "address": ("호칭·관계", "address")}
_BY_LABEL = {label: kind for kind, pair in LABELS.items() for label in pair}
_LABEL = "|".join(re.escape(label) for label in _BY_LABEL)
# `[NMOS <label> · t<first>[–<last>] · <date>]` … `[/NMOS <label>]`: the closing label is the opening one
# (fixtures/unit/note-blocks-v1.json; the plugin's `stripNoteBlocks` is the same).
BLOCK = re.compile(r"\[NMOS (" + _LABEL + r")(?: · t(\d+)(?:–(\d+))?)?(?: · [^\]\n]*)?\]\n?[\s\S]*?\[/NMOS \1\]\n?")


def strip_blocks(text: str) -> tuple[str, list[dict[str, str]]]:
    """The note without NMOS's blocks, and each block's kind and turns ("0-87", "120"). A note without one comes back
    exactly as it was; an unclosed marker is not a block."""
    blocks = [{"kind": _BY_LABEL[m[1]], "turns": (m[2] + (f"-{m[3]}" if m[3] else "")) if m[2] else ""}
              for m in BLOCK.finditer(text)]
    if not blocks:
        return text, []
    return re.sub(r"\n{3,}", "\n\n", BLOCK.sub("\n\n", text)).strip(), blocks


def wrap(kind: str, body: str, turns: str, lang: str, today: str) -> str:
    """A section between its markers (`turns`: "0-87" or "120")."""
    label = LABELS[kind][lang == "en"]
    return f"[NMOS {label} · t{turns.replace('-', '–')} · {today}]\n{body.strip()}\n[/NMOS {label}]"
