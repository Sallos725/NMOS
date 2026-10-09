"""Changes without a cause (PHASE-39 Q4): a watched status value that changed while the reply's story did not say so.

A card that keeps a game's numbers in a status bar has the model recompute the bar every turn, and it gets it wrong in
ways a ledger can see: an item appears that nothing gave, a number moves that nothing spent. Between two neighbouring
values of a watched key (`state.history`), a read flags:

- (i) an item added to or dropped from a list value ("물약 ×2 / 해독제 ×1") that the reply's prose does not name;
- (ii) a number that changes, the value's words staying the same, where the prose names neither the key, nor the new
  number (in digits or in Korean words: "삼십만 원"), nor the difference;
- (iii) on a reply that was rerolled, swiped or edited, a value that goes back to the one two bars before while the
  single bar between said otherwise, unless the prose names the key or that value.

The prose is the reply without what the rules read (`parsers.prose`). Deterministic, no model call, nothing stored: a
flag is named by what it says (`flag_id`), and the owner's dismissal is an owner repair (`state_dismiss`, migration
0029). A rule without `watch` flags nothing.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any
from uuid import UUID

import psycopg

from .parsers import RuleSet, prose, watched
from .state import history

SPLIT = re.compile(r"\s*[/,·、]\s*")
COUNT = re.compile(r"\s*(?:[×xX*]\s*\d+|\(\s*\d+\s*\)|\d+\s*개)\s*$")  # "물약 ×2", "(3)", "3개"
BRACKETS = re.compile(r"\([^)]*\)|\[[^\]]*\]")
NUMBER = re.compile(r"(?<![\d.])-?\d[\d,]*(?:\.\d+)?")
# Korean amounts the story writes in words (PHASE-39 step 4, measured: a bar's +1,000,000 written in words): digits
# with 만, 억 or 조 ("100만", "1억 2천만"), and Hangul numerals before a unit of money or count ("삼십만 원", "삼십 골드").
HANGUL_DIGITS = {"일": 1, "이": 2, "삼": 3, "사": 4, "오": 5, "육": 6, "칠": 7, "팔": 8, "구": 9}
SMALL = {"십": 10, "백": 100, "천": 1000}
LARGE = {"만": 10**4, "억": 10**8, "조": 10**12}
_PART = r"\d[\d,]*\s?(?:[천백십]\s?[만억조]?|[만억조])"  # "3천", "2천만", "100만", "1억"
WITH_UNIT = re.compile(rf"(?<![\d,.]){_PART}(?:\s?{_PART})*")
HANGUL_AMOUNT = re.compile(r"(?<![가-힣\d])[일이삼사오육칠팔구십백천만억조]+\s?(?=원|골드|코인|개|포인트|점|레벨)")
WORD = re.compile(r"\w{2,}")
NOTHING = frozenset({"", "-", "—", "x", "none", "nothing", "empty", "n/a", "없음", "無", "없다", "비어있음", "비어 있음"})
REASONS = ("added", "dropped", "number", "reverted")


def _name(item: str) -> str:
    return COUNT.sub("", item).strip()


def items(value: str) -> dict[str, str] | None:
    """A value's items by name (counts aside; "없음" is no item), or None when a part names nothing: "120/150" and
    "1,500 G" are numbers, not lists."""
    parts = [p.strip() for p in SPLIT.split(value) if p.strip()]
    if any(not re.search(r"[^\W\d_]", _name(p)) for p in parts):
        return None
    return {_name(p): p for p in parts if _name(p).casefold() not in NOTHING}


def _listed(old: str, new: str) -> tuple[dict[str, str], dict[str, str]] | None:
    """Both values as lists, when one of them is a list: several items, or none ("없음") beside a named one. A single
    word becoming another ("숲" → "마을") is no list: a place or a condition, not what (i) checks."""
    a, b = items(old), items(new)
    if a is None or b is None:
        return None
    several = len(SPLIT.split(old.strip())) > 1 or len(SPLIT.split(new.strip())) > 1
    return (a, b) if several or (not a) != (not b) else None


def _numbers(text: str) -> list[str]:
    return [n.replace(",", "") for n in NUMBER.findall(text)]


def _hangul(text: str) -> int | None:
    """A Korean numeral ("이백", "천오백", "3천", "1억 2천만") as a number; None when it is not one."""
    total = section = 0
    num: int | None = None
    for ch in text.replace(",", "").replace(" ", ""):
        if ch.isdigit():
            num = (num or 0) * 10 + int(ch)
        elif ch in HANGUL_DIGITS:
            num = HANGUL_DIGITS[ch]
        elif ch in SMALL:
            section += (num if num is not None else 1) * SMALL[ch]
            num = None
        elif ch in LARGE:
            total += (section + (num or 0) or 1) * LARGE[ch]
            section, num = 0, None
        else:
            return None
    return total + section + (num or 0)


def _story_numbers(text: str) -> set[str]:
    out = {n.lstrip("-") for n in _numbers(text)}
    for m in (*WITH_UNIT.finditer(text), *HANGUL_AMOUNT.finditer(text)):
        if (n := _hangul(m.group(0))) is not None:
            out.add(str(n))
    return out


def _template(value: str) -> str:
    return NUMBER.sub("#", value).strip()


def _plain(n: float) -> str:
    return str(int(n)) if n == int(n) else f"{n:g}"


class Prose:
    """What a reply's story says, for the checks: words case-folded, numbers without their thousands commas."""

    def __init__(self, text: str):
        self.text = text.casefold()
        self.numbers = _story_numbers(text)

    def says(self, word: str) -> bool:
        """The word in the story: a Korean word anywhere (a particle follows it: 물약을), a Latin one as a word ("SP" is
        not the "sp" of "Response")."""
        if not word.isascii():
            return word in self.text
        return re.search(rf"(?<![a-z0-9]){re.escape(word)}(?![a-z0-9])", self.text) is not None

    def names(self, word: str) -> bool:
        """The word itself, or (a name of several words, or with a bracketed note) one of its words of two characters
        or more: the story says 물약 for "회복 물약(소)"."""
        word = word.strip().casefold()
        if not word:
            return False
        if self.says(word):
            return True
        return any(self.says(w) for w in WORD.findall(BRACKETS.sub(" ", word)) if not w.isdigit())

    def number(self, n: str) -> bool:
        return n.lstrip("-") in self.numbers


def _number_changes(old: str, new: str) -> list[tuple[str, str]]:
    """The numbers that changed, when only numbers changed: a value whose words changed too ("7층 회의실" → "1층 로비")
    is a place, not a count (measured: every such flag on the owner's chats was a place)."""
    if _template(old) != _template(new):
        return []
    a, b = _numbers(old), _numbers(new)
    if len(a) == len(b):
        return [(x, y) for x, y in zip(a, b) if float(x) != float(y)]
    return [("", y) for y in b if y not in a] or ([(a[-1], "")] if len(a) > len(b) else [])


def _says_number(story: Prose, key: str, old: str, new: str, item: str | None = None) -> bool:
    if story.names(key) or (item and story.names(item)):
        return True
    for x, y in _number_changes(old, new):
        if y and story.number(y):
            continue
        if x and y and story.number(_plain(abs(float(y) - float(x)))):
            continue
        return False
    return True


def changes(key: str, old: str, new: str, story: Prose) -> list[tuple[str, str | None]]:
    """(reason, item) for each change from `old` to `new` the story does not say (i, ii)."""
    out: list[tuple[str, str | None]] = []
    if (listed := _listed(old, new)) is not None:
        a, b = listed
        for name in b.keys() - a.keys():
            if not story.names(name):
                out.append(("added", name))
        for name in a.keys() - b.keys():
            if not story.names(name):
                out.append(("dropped", name))
        for name in a.keys() & b.keys():
            if a[name] != b[name] and not _says_number(story, key, a[name], b[name], name):
                out.append(("number", name))
        return out
    a, b = items(old), items(new)  # one item whose count changed ("회복 물약 x3" → "x2"): its name says it too
    one = next(iter(a)) if a and b and len(a) == 1 and a.keys() == b.keys() else None
    if _number_changes(old, new) and not _says_number(story, key, old, new, one):
        out.append(("number", None))
    return out


def flag_id(flag: Mapping[str, Any]) -> str:
    """A flag named by what it says, as a dismissal stores it: another reroll or edit shows a changed flag again."""
    said = json.dumps([flag["turn"], flag["key"], flag["reason"], flag.get("item"), flag["old"], flag["new"]],
                      ensure_ascii=False)
    return hashlib.sha256(said.encode()).hexdigest()[:16]


def detect(hist: Mapping[str, list[dict[str, Any]]], watch: Mapping[str, frozenset[str]],
           prose_of: Mapping[Any, str]) -> list[dict[str, Any]]:
    """The flags of the watched keys' histories, oldest first. `prose_of` maps a revision id to its reply's prose."""
    out: list[dict[str, Any]] = []
    for key, entries in hist.items():
        for k in range(1, len(entries)):
            e, before = entries[k], entries[k - 1]
            if key not in watch.get(e["rule_id"], ()):
                continue
            base = {"key": key, "rule_id": e["rule_id"], "old": before["value"], "new": e["value"], "turn": e["turn"],
                    "position": e["position"], "revision_id": e["revision_id"]}
            story = Prose(prose_of.get(e["revision_id"], ""))
            if (k >= 2 and e.get("redone") and entries[k - 2]["value"] == e["value"]
                    and before["position"] == before["last_position"]):
                # the story saying where it went back to explains it (measured: back to a place the reply names)
                if not (story.names(key) or story.names(e["value"])
                        or all(story.number(n) for n in _numbers(e["value"])) and _numbers(e["value"])):
                    out.append({**base, "reason": "reverted", "item": None})
                continue
            out += [{**base, "reason": reason, "item": item} for reason, item in changes(key, before["value"],
                                                                                        e["value"], story)]
    for f in out:
        f["id"] = flag_id(f)
    return sorted(out, key=lambda f: (f["position"], f["key"], f["reason"], f["item"] or ""))


def flags_of(conn: psycopg.Connection, head: UUID, ruleset: RuleSet, card: str | None,
             upto: int | None = None) -> list[dict[str, Any]]:
    """The flags of a chat's head (every one, dismissed or not)."""
    watch = watched(ruleset)
    if not watch:
        return []
    keys = sorted(set().union(*watch.values()))
    hist = history(conn, head, ruleset.version, upto, keys=keys, redone=True)
    revisions = sorted({e["revision_id"] for es in hist.values() for e in es[1:]}, key=str)
    if not revisions:
        return []
    rows = conn.execute("SELECT id, content, metadata FROM source_revision WHERE id = ANY(%s)", (revisions,)).fetchall()
    stories = {r["id"]: prose(ruleset, r["content"], (r["metadata"] or {}).get("role"),
                              (r["metadata"] or {}).get("saying"), card) for r in rows}
    return detect(hist, watch, stories)


def dismissed(repairs: list[dict[str, Any]]) -> set[str]:
    """The flags the owner dismissed (live `state_dismiss` repairs)."""
    return {str((r.get("target") or {}).get("id")) for r in repairs
            if r.get("kind") == "state_dismiss" and not r.get("removed_at")}


def target(flag: Mapping[str, Any]) -> dict[str, Any]:
    """What a dismissal stores: the flag as the Inspector showed it."""
    text = f"{flag['key']}: {flag['old']} → {flag['new']}" + (f" ({flag['item']})" if flag.get("item") else "")
    return {"id": flag["id"], "turn": flag["turn"], "key": flag["key"], "reason": flag["reason"],
            "item": flag.get("item"), "old": flag["old"], "new": flag["new"], "text": text}
