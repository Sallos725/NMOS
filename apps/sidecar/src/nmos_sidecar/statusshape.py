"""A status window found by its shape (PHASE-43 S1): a block whose fields are mostly `key=value` or `key: value`, at
least three of them. No regex to write. Values are returned raw; the rule parser cleans them as it cleans every value.

The shapes read:

- one line in brackets (`[..]`, `【..】`, `《..》`, `『..』`) with `|`-separated segments: a leading label such as
  `Status:` and a value holding its own [..] or (..) are allowed, and a `|` inside one of those does not split it;
- a bracketed block of one field per line (`[` or `【` only), a bracketed header line (`[상태창]`, `【서연 상태창】`) or a
  status-word header (`상태창`, `Status:`) followed by one field per line, or a ``` fence of field lines;
- a two-column Markdown table (`| HP | 80 |`), its header row left out when a `|---|---|` row follows it;
- the same shapes in an HTML status card, read as its text (`<style>`/`<script>` left out, block tags as line breaks,
  table cells as columns). A block's `start` and `end` index the message as given, HTML or not.

A run of `name: words` lines without a header is how a script writes dialogue, so it is never read as a window, and a
block whose values read mostly like speech is not one either.

A block's first segment or header that is a word and no field is its `entity` candidate (`[서연 | HP: 80 | …]`,
`[서연 상태창]`, but also `[교실 | 날짜: …]`): the shape alone cannot tell a character from a place. `fields` and `keys`
stay bare. Only `characters` makes a candidate a character: when one reply holds windows for two or more different
candidates, which is when their keys would otherwise overwrite each other, and then only for keys that are not about the
scene (`scene_only`: a date, time, place or weather is the scene's, not a character's). A window for one character keeps
its bare keys, as before the candidate existed, so stored state, pins and watches keep matching.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .statechange import SCENE_KEYS, base

MIN_FIELDS = 3
FIELD_SHARE = 0.6  # of a block's segments, at least this many must be fields
BLOCK_MAX = 4000  # characters between the brackets
KEY_MAX = 30
MERGE_MAX = 20  # a bare segment this short continues the field before it ("Status: 중독 | 출혈")
HEADER_MAX = 30
_FIELD = re.compile(r"^\s*(?P<key>[^:：=|｜\[\]\n]{1,%d}?)\s*[=:：]\s*(?P<value>.*?)\s*$" % KEY_MAX, re.S)
_LABEL = re.compile(r"^\s*(?P<label>[^:：=|｜]{1,20})[:：]\s*(?=[^:：=|｜]{1,%d}=)" % KEY_MAX)  # "Status:" before "date=…"
_NOT_A_KEY = re.compile(r"[.!?。…\"'“”‘’]")
_SPEECH = re.compile(r"[.!?。！？…~]\s*$|[\"“”「」]")
_BULLET = re.compile(r"^\s*(?:[-*+•·▶▷►◆◇■□●○★☆※]\s+)?")
_FENCE = re.compile(r"^\s*(?:```|~~~)")
_TABLE_RULE = re.compile(r"^:?-{3,}:?$")
_WORD = re.compile(r"[^\W\d_][^\W\d_'’·\-]*")  # one word of a name: letters, no digits
BRACKETS = {"[": "]", "【": "】", "《": "》", "『": "』"}
MULTILINE = frozenset("[【")  # 『..』 and 《..》 over several lines are quotations and titles, not windows
_NEST = {**BRACKETS, "(": ")", "（": "）", "{": "}", "「": "」"}
_CLOSERS = frozenset(_NEST.values())
# Words that name a window, not a character ("[서연 상태창]" is 서연's; "[상태창]" is no one's).
LABEL_WORDS = frozenset({
    "status", "stats", "stat", "state", "info", "information", "profile", "window", "card", "panel", "hud",
    "character", "char", "sheet",
    "상태", "상태창", "상태표", "스탯", "스테이터스", "정보", "프로필", "현황", "캐릭터", "창", "능력치", "시트",
})
_HEADER_SHAPE = re.compile(r"^\s*([\[【《])(?P<label>[^\]】》:：=|｜\n]{1,%d})[\]】》]\s*$" % HEADER_MAX)
_PLAIN_HEADER = re.compile(r"^\s*(?P<label>[^:：=|｜\[\]\n]{1,%d}?)\s*[:：]?\s*$" % HEADER_MAX)


@dataclass(frozen=True)
class Block:
    start: int  # the opening bracket (or the header, fence or first row)
    end: int  # after the closing bracket (or the last line)
    fields: tuple[tuple[str, str], ...]  # (key, raw value), in order; a repeated key keeps its last value
    entity: str | None = None  # its leading word or header's name: a candidate, made a character by `characters`
    classic: bool = False  # one line of fields in [..] in the message as written: the window PHASE-43 read

    @property
    def keys(self) -> frozenset[str]:
        return frozenset(k for k, _ in self.fields)


# --- HTML -------------------------------------------------------------------------------------------------------------

_HTML_HINT = re.compile(r"<\s*/?\s*[A-Za-z][^>\n]*>")
_BREAK_TAGS = (r"br|p|div|li|ul|ol|dl|dt|dd|h[1-6]|section|article|header|footer|aside|nav|main|table|thead|tbody|"
               r"tfoot|caption|blockquote|pre|hr|details|summary|figure|figcaption|center|form|fieldset")
_HTML_PLAIN = re.compile(
    r"(?P<drop><(?P<dropped>style|script)\b[^>]*>.*?</(?P=dropped)\s*>)"
    r"|(?P<cell></t[dh]\s*>\s*<t[dh]\b[^>]*>)"
    r"|(?P<line></?(?:tr|%s)\b[^>\n]*>)"
    r"|(?P<tag><[^>\n]+>)" % _BREAK_TAGS, re.I | re.S)  # a stray "<-" … "->" never spans lines
_HTML_TABLE = re.compile(
    r"(?P<drop><(?P<dropped>style|script)\b[^>]*>.*?</(?P=dropped)\s*>)"
    r"|(?P<row><tr\b[^>]*>)|(?P<close></t[dh]\s*>)|(?P<open><t[dh]\b[^>]*>)"
    r"|(?P<line></?(?:tr|%s)\b[^>\n]*>)"
    r"|(?P<tag><[^>\n]+>)" % _BREAK_TAGS, re.I | re.S)  # a stray "<-" … "->" never spans lines


def html_text(text: str, *, cell: str = " | ", line: str = "\n", rows: bool = False
              ) -> tuple[str, list[int], list[int]]:
    """The text of HTML: `<style>` and `<script>` blocks left out, block-level tags as `line`, other tags removed. Table
    cells are joined by `cell`, or with `rows` written as Markdown rows (`| HP | 80 |`). Consecutive breaks are one.
    Also, for each character of the result, where its source starts and ends in `text` (a tag's character maps to the
    whole tag), so a span found in the result is a span of `text`."""
    out: list[str] = []
    starts: list[int] = []
    ends: list[int] = []

    broke = False  # the last character out is a break a tag made
    cells = False  # the last thing out is a table's own markup (a row, a cell's edge)

    def emit(s: str, a: int, b: int) -> None:
        nonlocal broke
        for ch in s:
            out.append(ch)
            starts.append(a)
            ends.append(b)
        broke = s == line

    def raw(a: int, b: int) -> None:
        nonlocal broke, cells
        if cells and not text[a:b].strip():  # the markup's own whitespace between a table's tags
            if out:
                ends[-1] = b
            return
        cells = False
        for i in range(a, b):
            if broke and text[i].isspace():  # the markup's own indentation and newlines after a break: none
                ends[-1] = i + 1
                continue
            out.append(text[i])
            starts.append(i)
            ends.append(i + 1)
            broke = False

    at = 0
    for m in (_HTML_TABLE if rows else _HTML_PLAIN).finditer(text):
        raw(at, m.start())
        at = m.end()
        kind = m.lastgroup if m.lastgroup != "dropped" else "drop"
        cells = kind in ("row", "close", "open", "cell") or (cells and kind in ("line", "drop", "tag"))
        if kind == "drop" or kind == "tag":
            continue
        if kind == "line" or (rows and kind == "row"):
            if broke:  # consecutive breaks: one
                ends[-1] = m.end()
            else:
                emit(line, m.start(), m.end())
            if rows and kind == "row":
                emit("|", m.start(), m.end())
        elif kind == "cell":
            emit(cell, m.start(), m.end())
        elif kind == "close":
            emit(" |", m.start(), m.end())
        elif kind == "open":
            emit(" ", m.start(), m.end())
    raw(at, len(text))
    return "".join(out), starts, ends


# --- pieces -----------------------------------------------------------------------------------------------------------

def _outer(text: str, opener: str = "[") -> list[tuple[int, int]]:
    """(start, end) of each outermost balanced block of one bracket kind of at most BLOCK_MAX characters. Each kind is
    looked for on its own, so an unclosed 『 hides no [..] window."""
    closer = BRACKETS[opener]
    out: list[tuple[int, int]] = []
    depth, start = 0, -1
    for i, ch in enumerate(text):
        if ch == opener:
            if depth == 0:
                start = i
            depth += 1
        elif ch == closer and depth:
            depth -= 1
            if depth == 0:
                if 2 <= i - start <= BLOCK_MAX:
                    out.append((start, i + 1))
                start = -1
        if depth and i - start > BLOCK_MAX:  # an unclosed bracket: give up on it and look on
            depth, start = 0, -1
    return out


def _split(inner: str) -> list[str]:
    """`|`-separated segments, not splitting inside a nested [..], (..), 【..】 and the like. When the nesting does not
    balance, every `|` splits, as before nesting was read."""
    segments, stack, at = [], [], 0
    for i, ch in enumerate(inner):
        if ch in _NEST:
            stack.append(_NEST[ch])
        elif ch in _CLOSERS:
            if stack and stack[-1] == ch:
                stack.pop()
            else:
                return re.split(r"[|｜]", inner)
        elif ch in "|｜" and not stack:
            segments.append(inner[at:i])
            at = i + 1
    if stack:
        return re.split(r"[|｜]", inner)
    segments.append(inner[at:])
    return segments


def _field(segment: str) -> tuple[str, str] | None:
    m = _FIELD.match(segment.replace("\n", " "))
    key = m["key"].strip() if m else ""
    return (key, m["value"]) if key and not _NOT_A_KEY.search(key) else None


def entity_of(label: str) -> str | None:
    """The character a window's label names: its words without the window's own words ("서연 상태창" → "서연", "서연의
    상태창" → "서연"), at most three words of letters; None for a label that names no one ("상태창", "Day 3", "INFO")."""
    words = label.replace(":", " ").replace("：", " ").split()
    if not words or len(label) > HEADER_MAX:
        return None
    named = [w for w in words if w.casefold() not in LABEL_WORDS]
    labelled = len(named) < len(words)
    if not named or len(named) > 3:
        return None
    if labelled:  # a possessive before the window's word: "서연의 상태창", "Seoyeon's status"
        last = named[-1]
        for tail in ("'s", "’s", "의"):
            if last.endswith(tail) and len(last) > len(tail):
                named[-1] = last[: -len(tail)]
                break
    for w in named:
        if not _WORD.fullmatch(w) or (w.isascii() and w.isupper() and len(w) > 1):  # "HUD", "LBDATA": labels
            return None
    name = " ".join(named)
    return name if len(name) <= 20 else None


def _speechy(fields: list[tuple[str, str]]) -> bool:
    """Values that read mostly like speech: a script's `name: line`, not a window."""
    return 2 * sum(bool(_SPEECH.search(v)) for _, v in fields) >= len(fields)


def _make(start: int, end: int, fields: list[tuple[str, str]], entity: str | None) -> Block | None:
    kept = dict(fields)
    if len(kept) < MIN_FIELDS:
        return None
    return Block(start, end, tuple(kept.items()), entity)


def _lines(text: str) -> list[tuple[int, int]]:
    """(start, end) of each line, without its newline."""
    out, at = [], 0
    for m in re.finditer(r"\n", text):
        out.append((at, m.start()))
        at = m.end()
    out.append((at, len(text)))
    return out


# --- the shapes -------------------------------------------------------------------------------------------------------

def _bracketed(text: str) -> tuple[list[Block], list[Block]]:
    """The bracketed blocks: those read as PHASE-43 read them (one line of `|`-separated fields in [..]) first, then the
    other shapes."""
    first: list[Block] = []
    other: list[Block] = []
    for start, end in (span for opener in BRACKETS for span in _outer(text, opener)):
        inner = text[start + 1:end - 1]
        plain = re.split(r"[|｜]", inner)
        if len(plain) >= 2:
            block = _one_line(start, end, _split(inner))
            # every `|` splits when that reads more keys: a field inside the nested bracket ("[물약: 2 | 열쇠: 1]",
            # "(버프: 공격 | 방어: 10)") was a key before nesting was read, and a stored key does not go away
            flat = _one_line(start, end, plain)
            if flat is not None and (block is None or not flat.keys <= block.keys):
                block = flat
            if block is not None:
                if text[start] == "[":
                    first.append(Block(block.start, block.end, block.fields, block.entity, classic=True))
                else:
                    other.append(block)
        elif text[start] in MULTILINE and "\n" in inner.strip():
            if (block := _field_lines(start, end, inner.splitlines(), whole=True)) is not None:
                other.append(block)
    return first, other


def _one_line(start: int, end: int, segments: list[str]) -> Block | None:
    if len(segments) < MIN_FIELDS:
        return None
    entity = None
    label = _LABEL.match(segments[0])
    if label:
        entity = entity_of(label["label"])
        segments = [_LABEL.sub("", segments[0]), *segments[1:]]
    parsed = [_field(s) for s in segments]
    if parsed[0] is None and entity is None and (name := entity_of(segments[0].strip())):
        entity, segments, parsed = name, segments[1:], parsed[1:]  # "[서연 | HP: 80 | …]": the name is no field
    fields: list[tuple[str, str]] = []
    counted = 0
    for segment, f in zip(segments, parsed):
        bare = segment.strip()
        # "Status: 중독 | 출혈": one field of two words. Not after a number ("HP: 80 | 피곤함"): a count stays a count,
        # as the change line and the watches read it
        if (f is None and fields and bare and len(bare) <= MERGE_MAX and not _NOT_A_KEY.search(bare)
                and not re.search(r"\d", fields[-1][1])):
            key, value = fields[-1]
            fields[-1] = (key, f"{value} | {bare}")
            continue
        counted += 1
        if f is not None:
            fields.append(f)
    if len(dict(fields)) < FIELD_SHARE * counted:
        return None
    return _make(start, end, fields, entity)


def _field_lines(start: int, end: int, lines: list[str], *, whole: bool) -> Block | None:
    """A block of one field per line, the first line maybe a header naming the character. With `whole`, every line
    counts (FIELD_SHARE); otherwise the lines are all fields already."""
    rows = [_BULLET.sub("", ln).strip() for ln in lines]
    rows = [r for r in rows if r]
    if not rows:
        return None
    entity = None
    if _field(rows[0]) is None:
        head = _HEADER_SHAPE.match(rows[0])
        entity = entity_of(head["label"] if head else rows[0])
        if head or entity is not None or whole:
            rows = rows[1:]
    fields = [f for f in map(_field, rows) if f is not None]
    if not fields or _speechy(fields) or (whole and len(fields) < FIELD_SHARE * len(rows)):
        return None
    return _make(start, end, fields, entity)


def _header(line: str) -> tuple[bool, str | None]:
    """Whether a line heads a window, and the character it names: a bracketed label alone on its line, or a line of
    the window's own words ("상태창", "서연 상태창:", "Status")."""
    if m := _HEADER_SHAPE.match(line):
        return True, entity_of(m["label"])
    m = _PLAIN_HEADER.match(line)
    if m and any(w.casefold() in LABEL_WORDS for w in m["label"].replace("의", " ").split()):
        return True, entity_of(m["label"])
    return False, None


def _runs(text: str, tagged: frozenset[int] = frozenset()) -> list[Block]:
    """Header-led runs of field lines, ``` fences of them and two-column Markdown tables. With `tagged` (the newlines
    an HTML card's tags made), a run without a header counts when each of its lines ended at a tag."""
    found: list[Block] = []
    lines = _lines(text)
    i = 0
    while i < len(lines):
        a, b = lines[i]
        line = text[a:b]
        if _FENCE.match(line):
            close = next((j for j in range(i + 1, len(lines)) if _FENCE.match(text[slice(*lines[j])])), None)
            if close is not None:
                block = _field_lines(a, lines[close][1], [text[slice(*lines[j])] for j in range(i + 1, close)],
                                     whole=True)
                if block is not None:
                    found.append(block)
                i = close + 1
                continue
        if line.lstrip().startswith(("|", "｜")):
            j = i
            while j < len(lines) and text[slice(*lines[j])].lstrip().startswith(("|", "｜")):
                j += 1
            block = _table(text, lines[i:j])
            if block is not None:
                found.append(block)
            i = j
            continue
        is_header, entity = _header(line)
        first = i + 1 if is_header else i
        j = first
        fields: list[tuple[str, str]] = []
        while j < len(lines):
            row = _BULLET.sub("", text[slice(*lines[j])]).strip()
            f = _field(row) if row else None
            if f is None:
                break
            fields.append(f)
            j += 1
        headless = not is_header and j - first >= MIN_FIELDS and all(lines[k][1] in tagged for k in range(first, j - 1))
        if (is_header or headless) and fields and not _speechy(fields):
            block = _make(a, lines[j - 1][1], fields, entity)
            if block is not None:
                found.append(block)
                i = j
                continue
        # a run that is no window: look on after it, or at a header inside it
        i = next((k for k in range(i + 1, j) if _header(text[slice(*lines[k])])[0]), max(i + 1, j))
    return found


def _table(text: str, rows: list[tuple[int, int]]) -> Block | None:
    """A two-column Markdown table of `| key | value |` rows."""
    cells = [[c.strip() for c in re.split(r"[|｜]", text[a:b].strip().strip("|｜"))] for a, b in rows]
    if len(cells) > 1 and all(_TABLE_RULE.match(c) for c in cells[1]):
        cells = cells[2:]  # a header row and its rule
    cells = [c for c in cells if not all(_TABLE_RULE.match(x) for x in c)]
    if not cells or any(len(c) != 2 for c in cells):
        return None
    fields = [(k, v) for k, v in cells if k and len(k) <= KEY_MAX and not _NOT_A_KEY.search(k)]
    if len(fields) < len(cells) or _speechy(fields):
        return None
    return _make(rows[0][0], rows[-1][1], fields, None)


def _found(text: str, tagged: frozenset[int] = frozenset()) -> list[Block]:
    """Every shape's blocks, none overlapping another: a one-line [..] window wins any overlap (an enclosing 【..】 or a
    header's run of lines never hides the window PHASE-43 read inside it), then the earlier and longer block."""
    first, other = _bracketed(text)
    return _disjoint(first, other + _runs(text, tagged))


def _disjoint(first: list[Block], other: list[Block] = ()) -> list[Block]:
    out: list[Block] = []
    for group in (first, other):
        for b in sorted(group, key=lambda x: (x.start, -x.end)):
            if not any(b.start < o.end and o.start < b.end for o in out):
                out.append(b)
    return sorted(out, key=lambda x: x.start)


def blocks(text: str) -> list[Block]:
    """The status-shaped blocks of a message, in order. An HTML card is read as its text; a block found there is
    returned with its place in the message, and one that overlaps a block of the message as written is left out."""
    found = _found(text)
    if _HTML_HINT.search(text):
        plain, starts, ends = html_text(text, rows=True)
        if plain != text:
            tagged = frozenset(i for i, ch in enumerate(plain) if ch == "\n" and text[starts[i]] == "<")
            for b in _found(plain, tagged):
                if b.end <= b.start:
                    continue
                raw = Block(starts[b.start], ends[b.end - 1], b.fields, b.entity)  # never classic: read from HTML
                if not any(raw.start < o.end and o.start < raw.end for o in found):
                    found.append(raw)
            found = sorted(found, key=lambda x: x.start)
    return found


# A scene's keys, never a character's: the clock and place keys (`statechange.SCENE_KEYS`) and the weather and season.
SCENE_ONLY = SCENE_KEYS | frozenset({"날씨", "weather", "계절", "season", "요일", "weekday", "day"})


def scene_only(key: str) -> bool:
    """A key about the scene, never prefixed with a character (`Status.날씨` too: its last part, as `statechange.base`)."""
    return base(key) in SCENE_ONLY


def characters(found: list[Block]) -> list[str | None]:
    """The character each window of one reply is about, or None: a block's `entity` candidate only when the reply holds
    windows of two or more different candidates that share a key that is not about the scene (so `[서연 | HP …]` and
    `[도윤 | HP …]` are two characters, `[교실 | 날짜 …]` alone or `[교실 | 날짜 …]` with `[복도 | 날짜 …]` none)."""
    named = [b for b in found if b.entity]
    if len({b.entity for b in named}) < 2:
        return [None] * len(found)
    keys: dict[str, set[str]] = {}
    for b in named:
        keys.setdefault(b.entity, set()).update(k for k in b.keys if not scene_only(k))
    shared = {e for e in keys if any(keys[e] & keys[o] for o in keys if o != e)}
    return [b.entity if b.entity in shared else None for b in found]


def covers(found: frozenset[str], keys: frozenset[str]) -> bool:
    """Whether keys found name the window a key set names: at least three of them and most of them."""
    shared = len(found & keys)
    return shared >= MIN_FIELDS and shared >= FIELD_SHARE * len(keys)


def matches(block: Block, keys: frozenset[str]) -> bool:
    return covers(block.keys, keys)
