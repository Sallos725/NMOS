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
"""

from __future__ import annotations

from typing import Any

from .entities import USER_NAMES, Resolution, norm

PREDICATES = frozenset({"promised", "fulfilled"})  # the only assertions a thread opens, restates or closes
OPENING_MODALITIES = ("actual", "hypothetical")
# Overlap coefficient of character trigrams (|A∩B| / min(|A|, |B|)): a resolution often shortens the
# promise ("등대 앞에서 만나기" for "비가 그치면 내일 아침 등대 앞에서 만나기로 함"). The best match must
# reach MATCH_MIN and lead the next open thread of that maker by MATCH_MARGIN (ADR 0019).
MATCH_MIN = 0.6
MATCH_MARGIN = 0.15
# A new promise restates an open one only when one text contains the other ("등대 앞에서 만나기" in "비가
# 그치면 등대 앞에서 만나기로 함"). Similarity would merge different promises that share words ("등대 앞에서
# 만나기", "등대 앞에서 기다리기"), and would compare every new promise with every open one of its maker.
RESTATE_MIN_CHARS = 4


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


def opens(a: dict[str, Any], r: Resolution | None = None) -> bool:
    """Whether a `promised` assertion opens (or restates) a thread (Q2)."""
    if a["predicate"] != "promised" or a.get("polarity") == "negative":
        return False
    if a.get("modality", "actual") not in OPENING_MODALITIES:
        return False
    speaker = _speaker(a, r)
    return speaker is None or speaker == _maker(a, r)


def resolves(a: dict[str, Any], r: Resolution | None = None) -> bool:
    """Whether an assertion may close a thread (Q3): `fulfilled`, or a negative `promised`, actual, from
    the narration, or said by the maker or the promise's recipient."""
    if not (a["predicate"] == "fulfilled" or (a["predicate"] == "promised" and a.get("polarity") == "negative")):
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


def _match(a: dict[str, Any], open_by_maker: dict[str, list[dict[str, Any]]], r: Resolution | None) -> dict[str, Any] | None:
    """The one open thread `a` names, if exactly one: equal text first, else clearly the most similar."""
    recipient = _recipient(a, r)
    pool = [t for t in open_by_maker.get(_maker(a, r), ())
            if t["status"] == "open" and (recipient is None or t["_recipient"] == recipient)]
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
    """The one open thread of the same maker and recipient whose text contains, or is contained in, the new
    promise's text; None when there is none or more than one."""
    text = norm(a.get("value"))
    if len(text) < RESTATE_MIN_CHARS:
        return None
    recipient = _recipient(a, r)
    found = [t for t in open_by_maker.get(_maker(a, r), ()) if t["status"] == "open" and t["_recipient"] == recipient
             and len(t["_norm"]) >= RESTATE_MIN_CHARS and (text in t["_norm"] or t["_norm"] in text)]
    return found[0] if len(found) == 1 else None


def _ref(a: dict[str, Any]) -> dict[str, Any]:
    return {k: a.get(k) for k in ("id", "position", "turn", "predicate", "subject", "object", "value", "polarity",
                                  "source", "asserted_by", "evidence")}


def fold(rows: list[dict[str, Any]], r: Resolution | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]], set[int]]:
    """(threads newest first, unmatched resolutions, ids of the assertions the threads consumed).

    `rows` are the head's valid assertions in position order, then extraction order within a turn.
    """
    threads: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    used: set[int] = set()
    open_by_maker: dict[str, list[dict[str, Any]]] = {}  # every thread per maker; closed ones are skipped
    for a in rows:
        if opens(a, r):
            same = _restated(a, open_by_maker, r)
            if same is not None:
                same["restated"].append({"turn": a.get("turn"), "position": a["position"]})
            else:
                t = {"id": a["id"], "kind": "promise", "by": a["subject"], "to": a.get("object"), "text": a.get("value"),
                     "turn": a.get("turn"), "position": a["position"], "host_logical_id": a.get("host_logical_id"),
                     "source": a.get("source"), "modality": a.get("modality"), "evidence": a.get("evidence"),
                     "knowledge": a.get("knowledge"), "known_by": a.get("known_by"), "hidden_from": a.get("hidden_from"),
                     "names": a.get("names") or [a["subject"], *([a["object"]] if a.get("object") else [])],
                     "status": "open", "closed_by": None, "restated": [],
                     "_maker": _maker(a, r), "_recipient": _recipient(a, r), "_norm": norm(a.get("value"))}
                threads.append(t)
                open_by_maker.setdefault(t["_maker"], []).append(t)
            used.add(a["id"])
        elif resolves(a, r):
            target = _match(a, open_by_maker, r)
            if target is None:
                unmatched.append(_ref(a))
            else:
                target["status"] = "kept" if a["predicate"] == "fulfilled" else "broken"
                target["closed_by"] = _ref(a)
            used.add(a["id"])
    for t in threads:
        for k in ("_maker", "_recipient", "_norm", "_grams"):
            t.pop(k, None)
    threads.sort(key=lambda t: t["position"], reverse=True)
    unmatched.sort(key=lambda u: u["position"], reverse=True)
    return threads, unmatched, used


def relevant_threads(threads: list[dict[str, Any]], query: str, previous_ai: str, in_context: set[str],
                     limit: int, persona: frozenset[str] = frozenset()) -> list[dict[str, Any]]:
    """Open threads whose maker or recipient is mentioned now (Q5): in the user's message first, then in
    the previous reply; newest first within each. The persona does not count as a mention (it is in
    every chat; `persona` adds the names the host reported for it, ADR 0023), and a thread whose opening
    message is still in the prompt is left out (D3)."""
    q, ai = norm(query), norm(previous_ai)
    scored = []
    for t in threads:
        if t["status"] != "open" or t.get("host_logical_id") in in_context:
            continue
        names = {norm(n) for n in t["names"] if n} - USER_NAMES - persona
        names = {n for n in names if len(n) >= 2}
        mention = 2 if any(n in q for n in names) else (1 if any(n in ai for n in names) else 0)
        if mention:
            scored.append((mention, t["position"], t))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [t for _, _, t in scored[:limit]]
