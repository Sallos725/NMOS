"""A status window found by its shape (PHASE-43 S1): an outermost bracketed block whose `|`-separated segments are mostly
`key=value` or `key: value` fields, at least three of them. No regex to write; a leading label such as `Status:` and a
value holding its own [..] are allowed. Values are returned raw; the rule parser cleans them as it cleans every value."""

from __future__ import annotations

import re
from dataclasses import dataclass

MIN_FIELDS = 3
FIELD_SHARE = 0.6  # of a block's segments, at least this many must be fields
BLOCK_MAX = 4000  # characters between the brackets
KEY_MAX = 30
_FIELD = re.compile(r"^\s*(?P<key>[^:：=|｜\[\]\n]{1,%d}?)\s*[=:：]\s*(?P<value>.*?)\s*$" % KEY_MAX, re.S)
_LABEL = re.compile(r"^\s*[^:：=|｜]{1,20}[:：]\s*(?=[^:：=|｜]{1,%d}=)" % KEY_MAX)  # "Status:" before "date=…"
_NOT_A_KEY = re.compile(r"[.!?。…\"'“”‘’]")


@dataclass(frozen=True)
class Block:
    start: int  # the opening bracket
    end: int  # after the closing bracket
    fields: tuple[tuple[str, str], ...]  # (key, raw value), in order; a repeated key keeps its last value

    @property
    def keys(self) -> frozenset[str]:
        return frozenset(k for k, _ in self.fields)


def _outer(text: str) -> list[tuple[int, int]]:
    """(start, end) of each outermost balanced [..] block of at most BLOCK_MAX characters."""
    out: list[tuple[int, int]] = []
    depth, start = 0, -1
    for i, ch in enumerate(text):
        if ch == "[":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "]" and depth:
            depth -= 1
            if depth == 0:
                if 2 <= i - start <= BLOCK_MAX:
                    out.append((start, i + 1))
                start = -1
        if depth and i - start > BLOCK_MAX:  # an unclosed bracket: give up on it and look on
            depth, start = 0, -1
    return out


def blocks(text: str) -> list[Block]:
    """The status-shaped blocks of a message, in order."""
    found: list[Block] = []
    for start, end in _outer(text):
        segments = re.split(r"[|｜]", text[start + 1:end - 1])
        if len(segments) < MIN_FIELDS:
            continue
        segments[0] = _LABEL.sub("", segments[0])
        fields: dict[str, str] = {}
        for segment in segments:
            m = _FIELD.match(segment.replace("\n", " "))
            key = m["key"].strip() if m else ""
            if key and not _NOT_A_KEY.search(key):
                fields[key] = m["value"]
        if len(fields) >= MIN_FIELDS and len(fields) >= FIELD_SHARE * len(segments):
            found.append(Block(start, end, tuple(fields.items())))
    return found


def covers(found: frozenset[str], keys: frozenset[str]) -> bool:
    """Whether keys found name the window a key set names: at least three of them and most of them."""
    shared = len(found & keys)
    return shared >= MIN_FIELDS and shared >= FIELD_SHARE * len(keys)


def matches(block: Block, keys: frozenset[str]) -> bool:
    return covers(block.keys, keys)
