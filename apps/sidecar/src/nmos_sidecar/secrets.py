"""Secrets at read time (PHASE-10, ADR 0033). Pure: no database, no model.

A secret is a valid assertion kept from someone: knowledge `limited` with a non-empty `hidden_from`, not
dreamed. It stays a secret for each character it is kept from until the story shows that character finding
it out: a `learned` assertion (subject: who found out; value: the secret's text as OPEN SECRETS listed it),
actual and positive, on a later turn. A reveal ends the secret for that character only.

The worker writes a reveal's value as "[turn N] <subject> <predicate>: <content>", the listed line with the
turn it came from. It ends (1) the open secret of that turn with the same head (subject and predicate) whose
content is closest, however it is worded now: a later re-extraction of that turn (a new generation, or history
extracted after the reveal) rewords it; and (2) every other open secret kept from that character whose head
matches and whose content is equal or reaches the thread match (trigram overlap MATCH_MIN, ADR 0019): the same
secret is often extracted again in later turns. A head is compared apart from the content because a shared
head alone ("엘피 goal:") made two secrets of one character look alike. No match ends nothing and is reported
as unmatched. Rule 1 holds only while the listed turn reads as it did when the reveal was extracted (the
reveal's `listed_hash` against the secret's `turn_hash`, ADR 0033 amendment 2): an edit of that turn can make
it a different secret, which the reveal did not report; only rule 2 can still match it.

Nothing is stored: secrets follow head membership, the served extractions and entity resolution, so an edit
or delete of the revealing turn restores the secret on the next read (invariant 7).
"""

from __future__ import annotations

import re
from typing import Any

from .entities import Resolution, norm
from .threads import MATCH_MIN, Event, fire, similarity

PREDICATE = "learned"
NOT_SECRETS = frozenset({PREDICATE, "also_called", "fulfilled"})


def secret_text(a: dict[str, Any]) -> str:
    """The text a secret is listed and matched by: the fact line without marks (facts.fact_text)."""
    parts = [a["subject"], a["predicate"].replace("_", " ")]
    if a.get("object"):
        parts.append(a["object"])
    text = " ".join(parts)
    return f"{text}: {a['value']}" if a.get("value") else text


HEAD_MIN = 0.8  # the head of a reworded reveal ("엘피 goal") may differ in spacing or an alias's spelling


TURN = re.compile(r"^\[turn (\d+)\] ")


def reveal_value(listed: dict[str, Any]) -> str:
    """The value the worker stores for a reveal of a listed secret: its text and the turn it came from."""
    return f"[turn {listed['turn']}] {listed['text']}"


def _split(text: str | None) -> tuple[int | None, str | None, str]:
    """(turn, head, content) of a reveal's value or a secret's text; None where it gives none."""
    text = str(text or "")
    m = TURN.match(text)
    turn = int(m.group(1)) if m else None
    head, sep, body = norm(text[m.end():] if m else text).partition(": ")
    return (turn, head, body) if sep else (turn, None, head)


def _heads(sh: str | None, rh: str | None) -> bool:
    return rh is None or rh == sh or (sh is not None and similarity(rh, sh) >= HEAD_MIN)


def matches(secret: str, reveal: str | None) -> bool:
    """The content rule (2): head as given, content equal or similar."""
    (_, sh, sb), (_, rh, rb) = _split(secret), _split(reveal)
    return _heads(sh, rh) and bool(rb) and (rb == sb or similarity(rb, sb) >= MATCH_MIN)


def _hits(pool: list[dict[str, Any]], reveal: str | None, listed_hash: str | None = None) -> list[dict[str, Any]]:
    """Open secrets a reveal ends: the closest of its listed turn with the same head (rule 1), while that turn
    reads as it did when the reveal was extracted (`listed_hash`; None: not recorded), and every one the content
    rule matches (rule 2)."""
    turn, rh, rb = _split(reveal)
    hits = [s for s in pool if matches(s["text"], reveal)]
    same = [s for s in pool if turn is not None and s["turn"] == turn and rh is not None and _heads(_split(s["text"])[1], rh)
            and (listed_hash is None or s.get("turn_hash") in (None, listed_hash))]
    if same:
        scored = [(similarity(_split(s["text"])[2], rb), s) for s in same]
        best = max(score for score, _ in scored)
        hits += [s for score, s in scored if score == best and s not in hits]
    return hits


def _who(r: Resolution | None, name: str | None) -> str:
    return r.key("character", name) if r else "text:" + norm(name)


def is_secret(a: dict[str, Any]) -> bool:
    return (a["predicate"] not in NOT_SECRETS and a.get("knowledge") == "limited" and bool(a.get("hidden_from"))
            and a.get("modality", "actual") != "dreamed")


def reveals(a: dict[str, Any]) -> bool:
    """Whether an assertion reports that its subject found a secret out."""
    return (a["predicate"] == PREDICATE and a.get("modality", "actual") == "actual"
            and a.get("polarity", "positive") != "negative")


def _ref(a: dict[str, Any]) -> dict[str, Any]:
    return {k: a.get(k) for k in ("id", "position", "turn", "subject", "value", "source", "asserted_by", "evidence")}


def fold(rows: list[dict[str, Any]], r: Resolution | None = None,
         events: list[Event] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]], set[int]]:
    """(secrets newest first, unmatched reveals, ids of the `learned` assertions read).

    `rows` are the head's valid assertions in position order, then extraction order within a turn. Each
    secret: id, text, turn, position, holders (known_by), kept_from (every name it was kept from), ended
    ({name: the revealing assertion}), open (the names it is still kept from). `events` happen after every row of
    their turn, so a later reveal still ends a secret: the owner's repairs (ADR 0044).
    """
    secrets: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    used: set[int] = set()
    pending = sorted(events or [], key=lambda e: (e[0], e[1]))
    for a in rows:
        if a.get("turn") is not None:
            fire(pending, secrets, a["turn"])
        if is_secret(a):
            kept = {}
            for name in a["hidden_from"]:
                kept.setdefault(_who(r, name), name)
            secrets.append({"id": a["id"], "text": secret_text(a), "turn": a.get("turn"), "turn_hash": a.get("turn_hash"),
                            "subject": a["subject"], "predicate": a["predicate"],
                            "position": a["position"],
                            "host_logical_id": a.get("host_logical_id"), "holders": list(a.get("known_by") or []),
                            "kept_from": list(kept.values()), "ended": {}, "_kept": kept})
        elif reveals(a):
            used.add(a["id"])
            who = _who(r, a["subject"])
            hit = _hits([s for s in secrets if who in s["_kept"]], a.get("value"), a.get("listed_hash"))
            if not hit:
                unmatched.append(_ref(a))
            for s in hit:  # a secret this character already found out stays ended by the first reveal
                s["ended"].setdefault(s["_kept"][who], _ref(a))
    fire(pending, secrets, None)
    for s in secrets:
        s["open"] = [n for n in s["kept_from"] if n not in s["ended"]]
        s.pop("_kept")
    secrets.sort(key=lambda s: s["position"], reverse=True)
    unmatched.sort(key=lambda u: u["position"], reverse=True)
    return secrets, unmatched, used
