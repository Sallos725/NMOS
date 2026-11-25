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
head alone ("루카 goal:") made two secrets of one character look alike; a line whose predicate takes no value
("김하나 possesses 독약") has its object as the content, and two heads compare by subject, predicate and object, not
as one string ("김서연 …" is not "김서윤 …"). Rule 1 takes a secret sharing nothing with the reveal's content only
when it is the one secret of that turn with the head and its content is not an object name (RULE1_FLOOR): a
secret the re-extraction left out does not end another one of its turn. No match ends nothing and is reported
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
from .predicates import REGISTRY, address_label, address_slot
from .threads import MATCH_MIN, Event, fire, similarity

PREDICATE = "learned"
# PHASE-66: what a character believes (true or not) or forgot is no fact about the world, so never a secret, and a belief
# is never knowing: a secret about a matter someone merely believes stays kept from them
EPISTEMIC = frozenset({"believes", "forgot"})
NOT_SECRETS = frozenset({PREDICATE, "also_called", "fulfilled",
                         # PHASE-60 S8, owner decision 2026-11-23: a told row keeps its marks, but no reveal check
                         # tracks it; a known limit of this phase
                         "told"}) | EPISTEMIC


def secret_text(a: dict[str, Any]) -> str:
    """The text a secret is listed and matched by: the fact line without marks (facts.fact_text)."""
    parts = [a["subject"], a["predicate"].replace("_", " ")]
    if a.get("object"):
        parts.append(a["object"])
    text = " ".join(parts)
    if label := address_label(a):
        text = f"{text} [{label}]"
    return f"{text}: {a['value']}" if a.get("value") else text


HEAD_MIN = 0.8  # the head of a reworded reveal ("루카 goal") may differ in spacing or an alias's spelling
# Rule 1 floor (exclusive). The one secret of the listed turn with the head is that secret however it is worded now
# (ADR 0033 amendment 2). Of two or more, the closest must share something with the reveal's content: a reworded turn
# still shares a trigram or two (0.08 on the owner's example), and at 0.0 every one of them tied and ended. A head
# without a value (`possesses`, ...) has an object name for content: there 0.0 is another item, never a rewording.
RULE1_FLOOR = 0.0


TURN = re.compile(r"^\[turn (-?\d+)\] ")  # -1: a carried secret, from before turn 0 (ADR 0085)
# The predicate words of a secret's text (`secret_text`), longest first ("feels toward" before a shorter one). A
# predicate without a value (`possesses`, `located_in`, `member_of`) has no ": " in its text: its object is the content.
_WORDS = tuple(sorted({p.replace("_", " ") for p in REGISTRY}, key=len, reverse=True))
ADDRESSES = "addresses"  # the predicate words of the one predicate whose head can carry a label (PHASE-64)
_VALUELESS = tuple(sorted({p.replace("_", " ") for p, d in REGISTRY.items() if not d.needs_value}, key=len, reverse=True))


def reveal_value(listed: dict[str, Any]) -> str:
    """The value the worker stores for a reveal of a listed secret: its text and the turn it came from."""
    return f"[turn {listed['turn']}] {listed['text']}"


def _split(text: str | None) -> tuple[int | None, str | None, str]:
    """(turn, head, content) of a reveal's value or a secret's text; None where it gives none. A line without ": "
    whose predicate takes no value ("김하나 possesses 독약") has its subject and predicate as the head and its object as
    the content: compared whole, two belongings of one character shared most of their text and one reveal ended both."""
    text = str(text or "")
    m = TURN.match(text)
    turn = int(m.group(1)) if m else None
    line = norm(text[m.end():] if m else text)
    head, sep, body = line.partition(": ")
    if sep:
        # A conditional form of address (PHASE-64) has its label in the head ("X addresses Y [label]: content"), and
        # the label may hold ": " itself: such a head ends at the label's "]: ". What is stored stays as it is.
        i = line.find(" [")
        if 0 < i < len(head) and (end := line.find("]: ", i)) > 0 and (p := _parts(line[:i])) is not None \
                and p[1] == ADDRESSES:
            return turn, line[:end + 1], line[end + 3:]
        return turn, head, body
    for words in _VALUELESS:
        i = line.find(f" {words} ")
        if i > 0:
            return turn, line[:i + len(words) + 1], line[i + len(words) + 2:]
    return turn, None, line


def _parts(head: str) -> tuple[str, str, str] | None:
    """(subject, predicate words, object) of a head, or None when it names no predicate."""
    for words in _WORDS:
        for i in (m.start() for m in re.finditer(re.escape(f" {words}"), head)):
            end = i + len(words) + 1
            if i > 0 and (end == len(head) or head[end] == " "):
                return head[:i], words, head[end:].strip()
    return None


def _same_name(a: str, b: str, r: Resolution | None) -> bool:
    """Two spellings of a head's subject or object are one name: equal apart from spacing, one entity, or as close as a
    head must be. A whole head compared alone let two characters whose names differ by a syllable ("김서연", "김서윤")
    share a long predicate and pass."""
    if a.replace(" ", "") == b.replace(" ", ""):
        return True
    if not a or not b:
        return False
    if r is not None:
        ka, kb = r.key("character", a), r.key("character", b)
        if not ka.startswith("text:") and not kb.startswith("text:"):
            return ka == kb
    return similarity(a, b) >= HEAD_MIN


def _unlabel(head: str) -> tuple[str, str | None]:
    """(head without its label, the label) of a conditional form of address's head ("x addresses y [label]",
    PHASE-64); (head, None) for any other head. The label is not part of the object's name."""
    i = head.find(" [")
    if i > 0 and head.endswith("]") and (p := _parts(head[:i])) is not None and p[1] == ADDRESSES and p[2]:
        return head[:i], head[i + 2:-1].strip()
    return head, None


# The labels `secret_text` gives a public or private form of address without a `when` (either language), by scope.
_SCOPE_OF = {norm(address_label({"predicate": ADDRESSES, "address_condition": {"scope": scope, "when": None}}, lang)):
             scope for scope in ("public", "private") for lang in (None, "ko")}


def _label_slot(label: str | None) -> tuple[str, ...]:
    """What a label's text says of its slot: `default` without one, the scope of a scope's own label, else only the
    phrase (a `when`: of a public, private or situational form, which the text does not say)."""
    if label is None:
        return ("default",)
    return (_SCOPE_OF[label],) if label in _SCOPE_OF else ("phrase", label)


def _same_slot(label: str | None, slot: tuple[str, ...] | None, other: str | None) -> bool | None:
    """Whether a reveal's label `other` names the slot of the secret with label `label` and, when its row is at hand,
    slot `slot` (`predicates.address_slot`), one slot as Phase 64 folds them: public and private by scope, a situational
    form by its `when` exactly as folded, the default without a condition. None when the text cannot tell, as a
    re-extraction of the listed turn leaves it (`_hits` rule 1, unique only): a phrase other than the secret's own
    against a public or private secret (a phrase does not say its scope), or a condition one side has and the other has
    not (added or dropped by the re-extraction, or a reveal recorded before extract-v20). Never a scope's label against
    the other scope or a situational form, nor another `when` against a situational form. Without the row (a listing's
    text alone) only an equal label matches."""
    theirs = _label_slot(other)
    if slot is None:
        return theirs == _label_slot(label)
    if theirs == slot:
        return True
    if slot == ("default",) or theirs == ("default",):
        return None
    if slot[0] == "situational":
        return theirs == ("phrase", slot[1])
    if theirs[0] == "phrase":  # against a public or private secret
        return True if theirs[1] == label else None
    return False  # the other scope's label


def _heads(sh: str | None, rh: str | None, r: Resolution | None = None,
           slot: tuple[str, ...] | None = None) -> bool | None:
    """Whether a reveal's head `rh` is a secret's head `sh`: subject, predicate and object compared as names, and for a
    form of address its label's slot (`_same_slot`) apart from them; None when the names are and the slot cannot be
    told."""
    if rh is None or rh == sh:
        return True
    if sh is None:
        return False
    (bs, ls), (br, lr) = _unlabel(sh), _unlabel(rh)
    ps, pr = _parts(bs), _parts(br)
    if ps is not None and pr is not None:
        same = ps[1] == pr[1] and _same_name(ps[0], pr[0], r) and (ps[2] == pr[2] or _same_name(ps[2], pr[2], r))
    else:
        same = similarity(br, bs) >= HEAD_MIN
    if not same:
        return False
    if ps is None or ps[1] != ADDRESSES:
        return True
    return _same_slot(ls, slot, lr)


def matches(secret: str, reveal: str | None, r: Resolution | None = None,
            slot: tuple[str, ...] | None = None) -> bool:
    """The content rule (2): head as given (a slot that cannot be told is not), content equal or similar."""
    (_, sh, sb), (_, rh, rb) = _split(secret), _split(reveal)
    return _heads(sh, rh, r, slot) is True and bool(rb) and (rb == sb or similarity(rb, sb) >= MATCH_MIN)


def _hits(pool: list[dict[str, Any]], reveal: str | None, listed_hash: str | None = None,
          r: Resolution | None = None) -> list[dict[str, Any]]:
    """Open secrets a reveal ends: the closest of its listed turn with the same head (rule 1), while that turn
    reads as it did when the reveal was extracted (`listed_hash`; None: not recorded) and its content shares
    something with the reveal's (RULE1_FLOOR), and every one the content rule matches (rule 2)."""
    turn, rh, rb = _split(reveal)
    hits = [s for s in pool if matches(s["text"], reveal, r, s.get("_slot"))]
    heads = [(s, _heads(_split(s["text"])[1], rh, r, s.get("_slot"))) for s in pool
             if turn is not None and s["turn"] == turn and rh is not None
             and (listed_hash is None or s.get("turn_hash") in (None, listed_hash))]
    same = [s for s, head in heads if head]
    if not same:
        # A form of address whose label the re-extraction worded anew (PHASE-64; coordinator decision 2026-11-25): a public
        # or private secret of the listed turn whose slot the label cannot tell is it only when it is the one such
        # secret. With two (a public and a private one of the pair), neither ends: the secret stays hidden, fail-safe,
        # and a repair can end it.
        loose = [s for s, head in heads if head is None]
        same = loose if len(loose) == 1 else []
    if same:
        scored = [(similarity(_split(s["text"])[2], rb), s) for s in same]
        best = max(score for score, _ in scored)
        if best > RULE1_FLOOR or (len(same) == 1 and not _valueless(reveal)):
            hits += [s for score, s in scored if score == best and s not in hits]
    return hits


def _valueless(text: str | None) -> bool:
    """A line whose head `_split` found by a predicate without a value: no ": " in it."""
    return ": " not in str(text or "") and _split(text)[1] is not None


def _who(r: Resolution | None, name: str | None) -> str:
    return r.key("character", name) if r else "text:" + norm(name)


def is_secret(a: dict[str, Any]) -> bool:
    return (a["predicate"] not in NOT_SECRETS and a.get("knowledge") == "limited" and bool(a.get("hidden_from"))
            and a.get("modality", "actual") != "dreamed")


def kept_from_others(a: dict[str, Any]) -> bool:
    """extract-v21 (PHASE-66): a fact known by the characters `known_by` names alone, with nobody in `hidden_from`
    (knowledge `limited` in its own four-way scope, `knowledge_scope`): it is kept from everyone else, a character who
    first appears later included, and ends for whoever learns it. A secret that names whom it is kept from (`limited`
    or `public_except` with `hidden_from`) is kept from those alone, as every earlier generation's secret is. A row of
    an earlier generation has no `knowledge_scope`, so its known-by-only facts are no secrets, as before."""
    return (a.get("knowledge_scope") == "limited" and a["predicate"] not in NOT_SECRETS
            and a.get("knowledge") == "limited" and bool(a.get("known_by")) and not a.get("hidden_from")
            and a.get("modality", "actual") != "dreamed")


def reveals(a: dict[str, Any]) -> bool:
    """Whether an assertion reports that its subject found a secret out."""
    return (a["predicate"] == PREDICATE and a.get("modality", "actual") == "actual"
            and a.get("polarity", "positive") != "negative")


def _forgets(a: dict[str, Any]) -> bool:
    """A narrated, actual, positive `forgot` (extract-v21): what `facts._epistemic` reads as one."""
    return (a["predicate"] == "forgot" and a.get("polarity", "positive") != "negative"
            and (a.get("source") or "narration") == "narration" and (a.get("modality") or "actual") == "actual")


def _ref(a: dict[str, Any]) -> dict[str, Any]:
    return {k: a.get(k) for k in ("id", "position", "turn", "subject", "value", "source", "asserted_by", "evidence")}


def _narrated(a: dict[str, Any]) -> bool:
    return (a.get("source") or "narration") == "narration" and (a.get("modality") or "actual") == "actual"


class _Groups:
    """Who belongs to a group named in a knowledge mark (extract-v21, PHASE-66). A name is a group when the read's
    resolution knows a `group` entity by it (an entity type, never a spelling): typed so by some row, such as the object
    of a `member_of`. Its members are the characters whose narrated, actual `member_of` it overlaps the secret's time:
    a member when the secret is stated, or one who joins later (covered from then on, as the read is of now). One who
    left before the secret is not covered; one who leaves after it is not un-told what they learned as a member (named
    in `known_by`), nor told what was kept from them (named in `hidden_from`)."""

    def __init__(self, rows: list[dict[str, Any]], r: Resolution | None):
        self.r = r
        self.said: dict[str, list[tuple[int, str, str, bool]]] = {}  # group key -> (turn, character key, name, joined)
        if r is None:
            return
        for a in rows:
            if a["predicate"] == "member_of" and a.get("object") and _narrated(a):
                turn = a.get("turn") if a.get("turn") is not None else -1
                self.said.setdefault(r.key("group", a["object"]), []).append(
                    (turn, _who(r, a["subject"]), a["subject"], a.get("polarity", "positive") != "negative"))

    def group(self, name: str, *, strict: bool) -> bool:
        """Whether a mark's name is a group. `strict` (a holder's): not when a character goes by it too, as the doubt
        then keeps the secret hidden."""
        if self.r is None or self.r.entity("group", name) is None:
            return False
        return not strict or self.r.entity("character", name) is None

    def members(self, name: str, since: int | None) -> dict[str, str]:
        """{character key: name} of the members whose membership overlaps the secret's time, from turn `since` on."""
        assert self.r is not None
        since = since if since is not None else -1
        state: dict[str, bool] = {}
        later: set[str] = set()
        names: dict[str, str] = {}
        for turn, k, n, joined in self.said.get(self.r.key("group", name), ()):
            names.setdefault(k, n)
            if turn <= since:
                state[k] = joined
            elif joined:
                later.add(k)
        return {k: names[k] for k in names if state.get(k) or k in later}


def _everyone(r: Resolution | None) -> dict[str, str]:
    """{key: name} of every character the read knows, the persona always among them: a secret kept from everyone but its
    holders is kept from each of them (`kept_from_others`)."""
    out: dict[str, str] = {}
    if r is None:
        return out
    for e in r.entities():
        if e["type"] == "character":
            out.setdefault(e["id"], e["name"])
    persona = _who(r, "{{user}}")
    if persona not in out:
        out[persona] = "{{user}}"
    return out


def _matter(value: str | None, s: dict[str, Any]) -> bool:
    """Whether a forgetting's named matter is this secret: its content or its line, at least MATCH_MIN alike (the bar
    `facts._about` reads a forgetting's matter by)."""
    matter = TURN.sub("", str(value or ""))
    return bool(matter.strip()) and max(similarity(matter, _split(s["text"])[2]), similarity(matter, s["text"])) >= MATCH_MIN


def _forgot(g: dict[str, Any], s: dict[str, Any], who: str, r: Resolution | None) -> None:
    """A forgetting (`g`) of its subject's: a secret that was ended for them (a reveal, or the owner's found-out) is kept
    from them again from its turn on, and ends again only when they learn it again. One kept from everyone but its
    holders is kept from a holder who forgets it too. `forgot_scope`: one matter, "all", or "since turn N" (of when they
    learned it: the reveal's turn, a holder's the secret's)."""
    from .facts import forgot_scope  # facts imports this module

    scope, since = forgot_scope(g.get("value"))

    def applies(start: int | None) -> bool:
        if start is not None and g.get("turn") is not None and start > g["turn"]:
            return False
        if scope == "all":
            return True
        if scope == "since":
            return start is not None and since is not None and start >= since
        return _matter(g.get("value"), s)

    for name in [n for n in s["ended"] if _who(r, n) == who]:
        if applies(s["ended"][name].get("turn")):
            s.setdefault("reopened", []).append({"to": name, "forgot": _ref(g), "ended": s["ended"].pop(name)})
    if s["_others"] and who in s["_holders"] and applies(s["turn"]):
        name = s["_holders"].pop(who)
        s["holders"] = [n for n in s["holders"] if _who(r, n) != who]
        if who not in s["_kept"]:
            s["_kept"][who] = name
            s["kept_from"].append(name)
        s.setdefault("reopened", []).append({"to": s["_kept"][who], "forgot": _ref(g), "held": True})


def _secret(a: dict[str, Any], r: Resolution | None, groups: _Groups | None) -> dict[str, Any]:
    kept: dict[str, str] = {}
    for name in a.get("hidden_from") or ():
        kept.setdefault(_who(r, name), name)
    holders = list(a.get("known_by") or [])
    out = {"id": a["id"], "text": secret_text(a), "turn": a.get("turn"), "turn_hash": a.get("turn_hash"),
           "subject": a["subject"], "predicate": a["predicate"], "object": a.get("object"),
           "position": a["position"],
           "host_logical_id": a.get("host_logical_id"), "holders": holders,
           "kept_from": [], "ended": {}, "_kept": kept, "_others": False, "_holders": {},
           "_evidence": a.get("evidence"),  # for a repair's quote (repairs.match_secret)
           "_slot": address_slot(a) if a["predicate"] == ADDRESSES else None}
    if groups is not None:  # extract-v21 (PHASE-66): its marks name groups, its `limited` is kept from everyone else
        held = {_who(r, n): n for n in holders}
        for name in a.get("known_by") or ():
            if groups.group(name, strict=True):
                for k, n in groups.members(name, a.get("turn")).items():
                    if k not in held:
                        held[k] = n
                        holders.append(n)
        for name in a.get("hidden_from") or ():
            if groups.group(name, strict=False):
                for k, n in groups.members(name, a.get("turn")).items():
                    if k not in held:
                        kept.setdefault(k, n)
        if kept_from_others(a):
            out["_others"] = True
            out["solo"] = True
            for k, n in _everyone(r).items():
                if k not in held:
                    kept.setdefault(k, n)
        out["_holders"] = held
    out["kept_from"] = list(kept.values())
    return out


def fold(rows: list[dict[str, Any]], r: Resolution | None = None,
         events: list[Event] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]], set[int]]:
    """(secrets newest first, unmatched reveals, ids of the `learned` assertions read).

    `rows` are the head's valid assertions in position order, then extraction order within a turn. Each
    secret: id, text, turn, position, holders (known_by), kept_from (every name it was kept from), ended
    ({name: the revealing assertion}), open (the names it is still kept from). `events` happen after every row of
    their turn, so a later reveal still ends a secret: the owner's repairs (ADR 0044).

    extract-v21 (PHASE-66), on its own rows only (`knowledge_scope`), so an earlier generation's read is as it was: a
    fact known by its holders alone is kept from every other character (`kept_from_others`, marked `solo`), one the read
    meets later included, and ends for whoever learns it; a group in
    a mark stands for its members (`_Groups`); a `believes` or `forgot` is never a secret nor a reveal (`EPISTEMIC`);
    and a `forgot` (any generation's secret) keeps a secret from its subject again (`_forgot`; `reopened`).
    """
    secrets: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    used: set[int] = set()
    pending = sorted(events or [], key=lambda e: (e[0], e[1]))
    groups: _Groups | None = None
    for a in rows:
        if a.get("turn") is not None:
            fire(pending, secrets, a["turn"])
        v21 = a.get("knowledge_scope") is not None
        if is_secret(a) or (v21 and kept_from_others(a)):
            if v21 and groups is None:
                groups = _Groups(rows, r)
            secrets.append(_secret(a, r, groups if v21 else None) | {"_row": a})
        elif reveals(a):
            used.add(a["id"])
            who = _who(r, a["subject"])
            hit = _hits([s for s in secrets if who in s["_kept"] or (s["_others"] and who not in s["_holders"])],
                        a.get("value"), a.get("listed_hash"), r)
            if not hit:
                unmatched.append(_ref(a))
            for s in hit:  # a secret this character already found out stays ended by the first reveal
                if who not in s["_kept"]:  # one kept from everyone but its holders: a character the listing did not name
                    s["_kept"][who] = a["subject"]
                    s["kept_from"].append(a["subject"])
                s["ended"].setdefault(s["_kept"][who], _ref(a))
        elif _forgets(a):
            who = _who(r, a["subject"])
            for s in secrets:
                _forgot(a, s, who, r)
    fire(pending, secrets, None)
    for s in secrets:
        s["open"] = [n for n in s["kept_from"] if n not in s["ended"]]
        row = s.pop("_row")
        if s["ended"] and row.get("hidden_from") is None:
            # A secret kept from everyone but its holders may name nobody in `hidden_from`; `facts.memory_view` drops a
            # revealed name from the row's list.
            row["hidden_from"] = []
        for k in ("_kept", "_evidence", "_slot", "_others", "_holders"):
            s.pop(k)
    secrets.sort(key=lambda s: s["position"], reverse=True)
    unmatched.sort(key=lambda u: u["position"], reverse=True)
    return secrets, unmatched, used
