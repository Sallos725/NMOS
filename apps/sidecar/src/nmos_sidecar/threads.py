"""Promise threads at read time (PHASE-7 Q2, Q3, Q5). Pure: no database, no model.

A promise is made by saying it, so a `promised` assertion opens a thread when the narration states it
or its maker says it (a claim whose speaker is its subject), with modality `actual` or `hypothetical`
(its content is in the future by nature). A promise someone else reports stays a claim, and a dreamed
or unknown one stays out, as before.

A thread closes when the story keeps it (`fulfilled`) or breaks, withdraws or releases it (a negative
`promised`), stated by the narration, the maker or the recipient. A resolution names the promise by its
text; it closes the one open thread of the same maker (and recipient, when it names one) whose text is
equal, or else clearly the most similar. No match, or a tie, closes nothing and is reported as
unmatched. A new promise whose text contains, or is contained in, an open one's restates it rather than
opening a second thread.

Nothing is stored: threads follow head membership, the served extractions and entity resolution, so an
edit or delete changes the next read.

Since `extract-v13` (PHASE-11, ADR 0039) goals, questions, threats and debts (`goal`, `question`, `threat`, `owes`)
are threads too, and `resolved` ends one with an outcome, matched by owner and text as promises are. Only rows of
`extract-v13` or later open them: earlier generations never report an end, so their goals stay facts. A new one
restates an open one of the same kind and owner when one text contains the other or they are as similar as a
resolution must be to match.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from .entities import USER_NAMES, Resolution, norm
from .variants import widened

KINDS = {"promised": "promise", "goal": "goal", "question": "question", "threat": "threat", "owes": "debt"}
PREDICATES = frozenset(KINDS) | {"fulfilled", "resolved"}  # the only assertions a thread opens, restates or closes
OPENING_MODALITIES = ("actual", "hypothetical")
SINCE = 13  # extract-v13: the first generation that reports how goals, questions, threats and debts end
# Overlap coefficient of character trigrams (|A∩B| / min(|A|, |B|)): a resolution often shortens the
# promise ("등대 앞에서 만나기" for "비가 그치면 내일 아침 등대 앞에서 만나기로 함"). The best match must
# reach MATCH_MIN and lead the next open thread of that maker by MATCH_MARGIN (ADR 0019).
MATCH_MIN = 0.6
MATCH_MARGIN = 0.15
# A new promise restates an open one only when one text contains the other ("등대 앞에서 만나기" in "비가
# 그치면 등대 앞에서 만나기로 함"). Similarity would merge different promises that share words ("등대 앞에서
# 만나기", "등대 앞에서 기다리기"), and would compare every new promise with every open one of its maker.
RESTATE_MIN_CHARS = 4
# packet-v4 (ADR 0019 amendment 1): a promise whose words the user's message repeats this much (share of the
# promise's trigrams) is what the message is about. On the owner's chat, "꼬옥 안아주면…" repeated an old hug
# promise at 0.26 while newer promises of the same girl scored 0.07 at most, and three newer ones filled the
# thread limit.
ABOUT_MIN = 0.2


def _grams(text: str | None) -> set[str]:
    padded = f"  {norm(text)} "
    return {padded[i: i + 3] for i in range(len(padded) - 2)}


def _overlap(ga: set[str], gb: set[str]) -> float:
    return len(ga & gb) / max(1, min(len(ga), len(gb)))


def similarity(a: str | None, b: str | None) -> float:
    return _overlap(_grams(a), _grams(b))


def _who(r: Resolution | None, entity_type: str | None, name: str | None) -> str:
    return r.key(entity_type, name) if r else "text:" + norm(name)


def _speaker(a: dict[str, Any], r: Resolution | None) -> str | None:
    """Entity key of a claim's speaker (a character), None for narration."""
    if a.get("source") != "character_claim":
        return None
    return _who(r, "character", a.get("asserted_by"))


def _maker(a: dict[str, Any], r: Resolution | None) -> str:
    return _who(r, a.get("subject_type"), a["subject"])


def _recipient(a: dict[str, Any], r: Resolution | None) -> str | None:
    return _who(r, a.get("object_type"), a["object"]) if a.get("object") else None


def _reports_ends(a: dict[str, Any]) -> bool:
    """Whether the generation that extracted `a` reports how its non-promise threads end (extract-v13 and later).
    A row without a compiler version (built in tests) counts as current."""
    compiler = a.get("compiler")
    if not compiler:
        return True
    number = str(compiler).rsplit("-v", 1)[-1]
    return number.isdigit() and int(number) >= SINCE


def opens(a: dict[str, Any], r: Resolution | None = None) -> bool:
    """Whether an assertion opens (or restates) a thread: a `promised` (Q2), or since extract-v13 a `goal`, `question`,
    `threat` or `owes`. Narrated, or said by its owner; a threat by anyone (the one who threatens says it); a debt by
    either side."""
    if a["predicate"] not in KINDS or a.get("polarity") == "negative":
        return False
    if a.get("modality", "actual") not in OPENING_MODALITIES:
        return False
    if a["predicate"] != "promised" and not _reports_ends(a):
        return False
    speaker = _speaker(a, r)
    if a["predicate"] == "threat":
        return True
    if a["predicate"] == "owes":
        return speaker is None or speaker in (_maker(a, r), _recipient(a, r))
    return speaker is None or speaker == _maker(a, r)


def resolves(a: dict[str, Any], r: Resolution | None = None) -> bool:
    """Whether an assertion may close a thread (Q3): `fulfilled`, a negative `promised`, or (extract-v13) a `resolved`
    with an outcome, actual, from the narration, or said by the owner or the thread's counterpart."""
    if a["predicate"] == "resolved":
        if not a.get("outcome"):
            return False
    elif not (a["predicate"] == "fulfilled" or (a["predicate"] == "promised" and a.get("polarity") == "negative")):
        return False
    if a.get("modality", "actual") != "actual":
        return False
    speaker = _speaker(a, r)
    return speaker is None or speaker in (_maker(a, r), _recipient(a, r))


def _grams_of(t: dict[str, Any]) -> set[str]:
    """A thread's trigrams, computed the first time a resolution needs them."""
    if "_grams" not in t:
        t["_grams"] = _grams(t["_norm"])
    return t["_grams"]


def _match(a: dict[str, Any], open_by_maker: dict[str, list[dict[str, Any]]], r: Resolution | None,
           promise: bool = True) -> dict[str, Any] | None:
    """The one open thread `a` names, if exactly one: equal text first, else clearly the most similar. `promise`:
    among promises (`fulfilled`, a negative `promised`), with the recipient when it names one; otherwise among goals,
    questions, threats and debts, by owner and text only (a `resolved` has no object, though models fill one in)."""
    recipient = _recipient(a, r) if promise else None
    pool = [t for t in open_by_maker.get(_maker(a, r), ())
            if t["status"] == "open" and (t["kind"] == "promise") == promise
            and (recipient is None or t["_recipient"] == recipient)]
    if not pool:
        return None
    text = norm(a.get("value"))
    equal = [t for t in pool if t["_norm"] == text]
    if equal:
        return equal[0] if len(equal) == 1 else None
    grams = _grams(text)
    scored = sorted(((_overlap(_grams_of(t), grams), t) for t in pool), key=lambda x: -x[0])
    if scored[0][0] < MATCH_MIN or (len(scored) > 1 and scored[0][0] - scored[1][0] < MATCH_MARGIN):
        return None
    return scored[0][1]


def _restated(a: dict[str, Any], open_by_maker: dict[str, list[dict[str, Any]]], r: Resolution | None) -> dict[str, Any] | None:
    """The one open thread of the same kind, maker and recipient whose text contains, or is contained in, the new
    one's text; for goals, questions, threats and debts also one as similar as a resolution must be (MATCH_MIN),
    since a turn often states the same aim twice in other words. None when there is none or more than one."""
    text = norm(a.get("value"))
    if len(text) < RESTATE_MIN_CHARS:
        return None
    kind = KINDS[a["predicate"]]
    recipient = _recipient(a, r) if kind in ("promise", "debt") else None  # others are one owner's
    pool = [t for t in open_by_maker.get(_maker(a, r), ()) if t["status"] == "open" and t["kind"] == kind
            and (recipient is None or t["_recipient"] == recipient) and len(t["_norm"]) >= RESTATE_MIN_CHARS]
    found = [t for t in pool if text in t["_norm"] or t["_norm"] in text]
    if not found and kind != "promise":
        grams = _grams(text)
        found = [t for t in pool if _overlap(_grams_of(t), grams) >= MATCH_MIN]
    return found[0] if len(found) == 1 else None


def _ref(a: dict[str, Any]) -> dict[str, Any]:
    return {k: a.get(k) for k in ("id", "position", "turn", "predicate", "subject", "object", "value", "polarity",
                                  "source", "asserted_by", "evidence", "outcome")}


Event = tuple[int, int, Callable[[list[dict[str, Any]]], None]]  # (turn, order, what happens to the threads then)


def fire(events: list[Event], items: list[dict[str, Any]], before_turn: int | None) -> None:
    """Run, in order, the events of turns before `before_turn` (all of them when None), removing them."""
    while events and (before_turn is None or events[0][0] < before_turn):
        events.pop(0)[2](items)


def fold(rows: list[dict[str, Any]], r: Resolution | None = None,
         events: list[Event] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]], set[int]]:
    """(threads newest first, unmatched resolutions, ids of the assertions the threads consumed).

    `rows` are the head's valid assertions in position order, then extraction order within a turn. `events` happen
    after every row of their turn, so later rows see them: the owner's repairs (ADR 0044).
    """
    threads: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    used: set[int] = set()
    pending = sorted(events or [], key=lambda e: (e[0], e[1]))
    open_by_maker: dict[str, list[dict[str, Any]]] = {}  # every thread per maker; closed ones are skipped
    for a in rows:
        if a.get("turn") is not None:
            fire(pending, threads, a["turn"])
        if opens(a, r):
            same = _restated(a, open_by_maker, r)
            if same is not None:
                same["restated"].append({"turn": a.get("turn"), "position": a["position"]})
            else:
                t = {"id": a["id"], "kind": KINDS[a["predicate"]], "by": a["subject"], "to": a.get("object"), "text": a.get("value"),
                     "turn": a.get("turn"), "turn_hash": a.get("turn_hash"), "position": a["position"],
                     "host_logical_id": a.get("host_logical_id"),
                     "source": a.get("source"), "modality": a.get("modality"), "evidence": a.get("evidence"),
                     "knowledge": a.get("knowledge"), "known_by": a.get("known_by"), "hidden_from": a.get("hidden_from"),
                     "revealed": a.get("revealed"), "repair": a.get("repair"),
                     "names": a.get("names") or [a["subject"], *([a["object"]] if a.get("object") else [])],
                     "status": "open", "closed_by": None, "restated": [],
                     "_maker": _maker(a, r), "_recipient": _recipient(a, r), "_norm": norm(a.get("value"))}
                threads.append(t)
                open_by_maker.setdefault(t["_maker"], []).append(t)
            used.add(a["id"])
        elif resolves(a, r):
            target = _match(a, open_by_maker, r, promise=a["predicate"] != "resolved")
            if target is None and a["predicate"] == "fulfilled":
                target = _match(a, open_by_maker, r, promise=False)  # a goal "fulfilled": models use either word
            if target is None:
                unmatched.append(_ref(a))
            elif target["kind"] == "promise":
                target["status"] = "kept" if a["predicate"] == "fulfilled" else "broken"
                target["closed_by"] = _ref(a)
            else:
                target["status"] = a["outcome"] if a["predicate"] == "resolved" else "achieved"
                target["closed_by"] = _ref(a)
            used.add(a["id"])
    fire(pending, threads, None)
    for t in threads:
        for k in ("_maker", "_recipient", "_norm", "_grams"):
            t.pop(k, None)
    threads.sort(key=lambda t: t["position"], reverse=True)
    unmatched.sort(key=lambda u: u["position"], reverse=True)
    return threads, unmatched, used


def relevant_threads(threads: list[dict[str, Any]], query: str, previous_ai: str, in_context: set[str],
                     limit: int, persona: frozenset[str] = frozenset(), about: bool = False,
                     aliases: Mapping[str, frozenset[str]] | None = None) -> list[dict[str, Any]]:
    """Open threads whose maker or recipient is mentioned now (Q5): in the user's message first, then in
    the previous reply; newest first within each. The persona does not count as a mention (it is in
    every chat; `persona` adds the names the host reported for it, ADR 0023), and a thread whose opening
    message is still in the prompt is left out (D3). With `about` (packet-v4), a promise whose words the
    user's message repeats (ABOUT_MIN) comes first, mentioned or not. `aliases`: the other names a character goes by in
    this request (ADR 0058)."""
    q, ai = norm(query), norm(previous_ai)
    q_grams = _grams(query) if about else set()
    scored = []
    for t in threads:
        if t["status"] != "open" or t.get("host_logical_id") in in_context:
            continue
        names = widened(t["names"], aliases) - USER_NAMES - persona
        names = {n for n in names if len(n) >= 2}
        mention = 2 if any(n in q for n in names) else (1 if any(n in ai for n in names) else 0)
        if about:
            words = _grams(t.get("text"))
            if len(words & q_grams) / max(1, len(words)) >= ABOUT_MIN:
                mention = 3
        if mention:
            scored.append((mention, t["position"], t))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [t for _, _, t in scored[:limit]]
