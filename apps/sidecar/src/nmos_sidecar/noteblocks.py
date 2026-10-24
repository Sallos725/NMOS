"""NMOS's block in a chat's author's note (PHASE-50 S5): its markers, and the note without it.

The author's note is canon (ADR 0045); the marked block is NMOS's own output and never canon. The plugin removes it
before it hashes the note, and `canonfacts.process` again before a read (an older plugin sends it whole). No imports
from the rest of the sidecar, so the canon reader can use it.
"""

from __future__ import annotations

import re

# `[NMOS note · t<turn> · <date>]` … `[/NMOS note]` (fixtures/unit/note-blocks-v1.json; the plugin's
# `stripNoteBlocks` is the same).
BLOCK = re.compile(r"\[NMOS note(?: · t(\d+))?(?: · [^\]\n]*)?\]\n?[\s\S]*?\[/NMOS note\]\n?")


def strip_blocks(text: str) -> tuple[str, list[dict[str, str]]]:
    """The note without NMOS's blocks, and the turn each was made at. A note without one comes back exactly as it was;
    an unclosed marker is not a block."""
    blocks = [{"turn": m[1] or ""} for m in BLOCK.finditer(text)]
    if not blocks:
        return text, []
    return re.sub(r"\n{3,}", "\n\n", BLOCK.sub("\n\n", text)).strip(), blocks


def wrap(body: str, turn: int | None, today: str) -> str:
    """The block between its markers. A marker inside the body (a summary or a reply that quotes one) is written with a
    parenthesis, so it can neither close the block early nor open another."""
    body = re.sub(r"\[(/?)NMOS ", r"(\1NMOS ", body.strip())
    return f"[NMOS note · t{turn if turn is not None else 0} · {today}]\n{body}\n[/NMOS note]"
