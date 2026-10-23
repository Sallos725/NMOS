"""NMOS's sections in a chat's author's note (PHASE-50 S5): their markers, and the note without them.

The author's note is canon (ADR 0045); a marked block is NMOS's own output and never canon. The plugin removes the
blocks before it hashes the note, and `canonfacts.process` again before a read (an older plugin sends them whole). No
imports from the rest of the sidecar, so the canon reader can use it.
"""

from __future__ import annotations

import re

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
    """A section between its markers (`turns`: "0-87" or "120"). A marker inside the body (a summary or a reply that
    quotes one) is written with a parenthesis, so it can neither close the block early nor open another."""
    label = LABELS[kind][lang == "en"]
    body = re.sub(r"\[(/?)NMOS ", r"(\1NMOS ", body.strip())
    return f"[NMOS {label} · t{turns.replace('-', '–')} · {today}]\n{body}\n[/NMOS {label}]"
