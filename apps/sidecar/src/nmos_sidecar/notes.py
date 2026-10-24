"""A note for the author's note (PHASE-50): one block the owner pastes into a chat's author's note, made on request.

It is written in English Markdown (amendment 2: the model reads the note, not a person), with names, titles and quoted
words as the chat writes them, and holds up to three parts the owner picks: the chronicle (the story's events, how they
went and ended, from the scene summaries and the threads; one model call, with an assembled fallback), what changed
from the setting (canon values a story fact now supersedes) and address and standing (each pair's relationship, role,
feeling and form of address). The block sits between two marker lines: the author's note is canon (ADR 0045), so the
canon never reads it (`noteblocks`).

Nothing is stored and no packet reads the note: it is a view of memory, made when asked.
"""

from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .config import Settings
from .entities import norm
from .facts import symmetric
from .inspector import _named, pairs, stale
from .llm import ChatModel, LLMError, metered
from .noteblocks import strip_blocks, wrap  # noqa: F401  (the API's names for them)
from .predicates import HOLDER_PER_ITEM, REGISTRY
from .summaries import content, held as summary_held, leaks

KINDS = ("chronicle", "changed", "address")  # the parts the owner can pick, in the note's order
PAIRS_MAX = 30  # address lines at most
CHANGED_MAX = 30  # changed lines at most, newest first
PAIRWISE = frozenset({"relationship", "role_toward", "feels_toward", "addresses"})
# A canon value a story fact can replace: single-valued predicates and an item's holder (PHASE-50 S3). A multi-valued
# one accumulates, so NMOS cannot tell a change from an addition there. `identity` is left out, as from the canon
# conflicts (ADR 0047 amendment 1): on the test install's copy 57 of a chat's 68 lines were a card's English identity
# told again in Korean or another true description ("Records clerk" → "중앙도서관 기록계"), not a change.
CHANGEABLE = (frozenset(p for p, d in REGISTRY.items() if d.cardinality == "single") | HOLDER_PER_ITEM) - {"identity"}
WORDS = {"located_in": "location", "has_status": "status", "relationship": "relationship", "role_toward": "role",
         "feels_toward": "feels", "addresses": "calls", "possesses": "held by", "destroyed": "destroyed"}
HEADER = ("# Story memory (NMOS, as of turn {turn})\n"
          "What the story has established so far. The latest messages take precedence over it.")
CHANGED_HEAD = ("## Changed from the setting\n"
                "The character card or lorebook still says the old value; the story has moved on.")
ADDRESS_HEAD = "## Address and standing"


def _w(key: str) -> str:
    return WORDS.get(key, key.replace("_", " "))


def kept(x: dict[str, Any]) -> bool:
    """Kept from someone. The note is read in every scene, so any limited fact counts (PHASE-50 S4)."""
    return x.get("knowledge") == "limited" or bool(x.get("hidden_from"))


def _secret_mark(x: dict[str, Any]) -> str:
    return f" (secret: {', '.join(x.get('hidden_from') or []) or 'someone'} does not know)"


def _said(e: dict[str, Any]) -> str:
    """What a statement says in its slot: an item's holder, else its value or object."""
    said = e.get("subject") if e["predicate"] in HOLDER_PER_ITEM else (e.get("value") or e.get("object") or "")
    return f"not {said}" if e.get("polarity") == "negative" else str(said)


def _head(f: dict[str, Any]) -> str:
    if f["predicate"] in HOLDER_PER_ITEM:
        return f"{f.get('object')} — {_w(f['predicate'])}"
    if f["predicate"] in PAIRWISE and f.get("object"):
        return f"{_named(f, 'subject')} → {_named(f, 'object')} — {_w(f['predicate'])}"
    return f"{_named(f, 'subject')} — {_w(f['predicate'])}"


def changes(facts: list[dict[str, Any]], secrets: bool = False) -> list[dict[str, Any]]:
    """Each canon value a current story fact replaced or ended (a canon entry of its history), newest first, said once:
    the fact, what the setting said and what it is now. With `secrets` off, nothing kept from someone. The author's
    note (`changed_lines`) and the panel's memory screen (PHASE-52) word them each their own way."""
    out: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for f in facts:
        if f.get("canon") or f["predicate"] not in CHANGEABLE or (kept(f) and not secrets):
            continue
        for h in f.get("history") or ():
            if not h.get("canon") or h.get("outcome") not in ("superseded", "ended") or (kept(h) and not secrets):
                continue
            old, new = _said(h), _said(f)
            key = (_head(f), old, new, f.get("turn"))
            if old == new or key in seen:  # the same line from two canon texts, or two spellings of one name
                continue
            seen.add(key)
            out.append({"fact": f, "old": old, "new": new})
    return out[:CHANGED_MAX]


def changed_lines(facts: list[dict[str, Any]], secrets: bool = False) -> list[str]:
    """`changes` as the author's note says them (English)."""
    return [f"- {_head(c['fact'])}: was {c['old']} → now {c['new']} (t{c['fact'].get('turn')})"
            + (" (fixed by the owner)" if c["fact"].get("repair") else "")
            + (_secret_mark(c["fact"]) if kept(c["fact"]) else "") for c in changes(facts, secrets)]


def address_lines(facts: list[dict[str, Any]], secrets: bool = False, excluded: frozenset[str] = frozenset()) -> list[str]:
    """One line per pair (`inspector.pairs`, newest first): the relationship, then each direction's role, feeling and
    form of address. With `secrets` off, nothing kept from someone; none with an end left out of the cast (PHASE-47)."""
    out = []
    for p in pairs([f for f in facts if secrets or not kept(f)], excluded)[:PAIRS_MAX]:
        bits = []
        for f in p["relationship"]:
            both = symmetric(f.get("value")) and len(p["relationship"]) == 1
            who = "" if both else f"{_named(f, 'subject')}→{_named(f, 'object')} "
            bits.append(f"{who}relationship {f.get('value')}" + (_secret_mark(f) if kept(f) else ""))
        for k, pred in (("role", "role_toward"), ("feels", "feels_toward"), ("speech", "addresses")):
            for f in p[k]:
                value = f'"{f.get("value")}"' if pred == "addresses" else f.get("value")
                bits.append(f"{_named(f, 'subject')}→{_named(f, 'object')} {_w(pred)} {value}"
                            + (_secret_mark(f) if kept(f) else ""))
        if bits:
            out.append(f"- {' ↔ '.join(sorted(p['names'].values()))}: " + " · ".join(bits))
    return out


INPUT_CHARS = 40_000  # the newest scene summaries the chronicle reads (PHASE-50 Q2 (a)); older turns by the story so far
NOW_MAX = 30  # "now" facts in the chronicle's input
NOW_PREDICATES = frozenset({"located_in", "has_status"})
CACHE_MAX = 64
_CACHE: OrderedDict[str, dict[str, Any]] = OrderedDict()  # model-written chronicles only, by their whole input
_CACHE_LOCK = threading.Lock()  # requests run in the server's thread pool
KIND_WORDS = {"debt": "debt", "promise": "promise", "goal": "goal", "question": "question", "threat": "threat"}

CHRONICLE_PROMPT = """You write a chronicle of a role-play chat, for its author's note: the user pastes it so that the
model writing the story keeps what happened in mind. You get SCENES (summaries in order, each with its turns), maybe
the STORY SO FAR (it covers turns before the first scene given), THREADS (promises, goals, questions, threats and
debts, each with its state and, when it ended, its outcome) and NOW (where characters are and how they are).

Write two parts in English, whatever the language of the chat; keep names, titles, places and quoted words exactly as
the input writes them:
- "events": the events in order, one line each starting with "- ": how it began, how it went, and how it ended or that
  it is still open, with its turns like (t12–20). A thread is told in the state THREADS gives it: never call an open one
  ended, never give an ended one another outcome.
- "now": where things stand, one line each starting with "- ".
Together at most {chars} characters. Only what the input says: no guesses, no judgments, no out-of-character notes.
{secrets}
Answer with JSON only: {{"events": "...", "now": "..."}}"""
SECRETS_KEPT = """
If OPEN SECRETS are listed, never write a secret's content, not even in other words or as a hint, and leave out the
object or act it is about: the note is read in every scene, in front of the characters it is kept from.
"""
SECRETS_TOLD = """
SECRETS are listed: you may write them, each marked with who does not know it, like "(secret: Kaito does not know)".
"""


def clear_cache() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()


def _cut_lines(text: str, cap: int) -> str:
    """At most `cap` characters, at a line end when one is in the last third."""
    text = text.strip()
    if len(text) <= cap:
        return text
    head = text[:cap]
    end = head.rfind("\n")
    return head[:end].rstrip() if end >= cap * 2 // 3 else head.rstrip()


def _thread_line(t: dict[str, Any]) -> str:
    who = f"{t['by']} → {t['to']}" if t.get("to") else str(t["by"])
    if t["status"] == "open":
        return f"- {who}: {t['text']} ({KIND_WORDS.get(t['kind'], t['kind'])}, since t{t.get('turn')})"
    closed = (t.get("closed_by") or {}).get("turn")
    return f"- {who}: {t['text']} → {t['status']}" + (f" (t{closed})" if closed is not None else "")


def _input(scenes: list[dict[str, Any]], story: dict[str, Any] | None, threads: list[dict[str, Any]],
           now: list[dict[str, Any]], secrets: list[dict[str, Any]], told_secrets: bool) -> str:
    lines: list[str] = []
    if secrets:
        lines += ["SECRETS:" if told_secrets else "OPEN SECRETS (never write their content):"]
        lines += [f"- {', '.join(s['holders'])} keep from {', '.join(s['open'])}: {content(s)}" for s in secrets] + [""]
    if story is not None:
        lines += [f"STORY SO FAR (turns {story['first_turn']}–{story['last_turn']}): {story['text']}", ""]
    lines += ["SCENES:"] + [f"[turns {s['first_turn']}–{s['last_turn']}] {s['text']}" for s in scenes] + [""]
    lines += ["THREADS:"] + [_thread_line(t) for t in threads] + [""]
    lines += ["NOW:"] + [f"- {_head(f)}: {_said(f)}" for f in now]
    return "\n".join(lines)


def chronicle(told: dict[str, Any] | None, threads: list[dict[str, Any]], facts: list[dict[str, Any]],
              secrets: list[dict[str, Any]], chars: int, model: Callable[..., tuple[Any, ...]] | None,
              told_secrets: bool = False, last_turn: int | None = None) -> dict[str, Any]:
    """The chronicle's Markdown (PHASE-50 S2): Events and Now from the model, or assembled from the summaries when there
    is no model or its replies fail; Open threads always from the stored threads. An open thread not said again for
    longer than its horizon allows (`inspector.stale`, the Inspector's "needs a look") is left out of both, and
    counted (amendment 3): the note is read every turn, and a lasting thread (PHASE-51) never goes stale.

    With `told_secrets` off, nothing kept from someone goes in. A scene summary or story is left out when the packet
    would hold it with every character a secret is kept from in the scene (`summaries.held`: it repeats a secret at
    LEAK_NEAR, or was written before a secret it should have been told about; the note is read in every scene), and a
    reply is refused when it repeats one at LEAK_NEAR (asked once more, then the assembled text)."""
    open_secrets = [s for s in secrets if s.get("open")]
    everyone = frozenset(norm(n) for s in open_secrets for n in s["open"])

    def tells(text: str) -> list[dict[str, Any]]:
        return [] if told_secrets else leaks(text, open_secrets, everyone)

    def holds(row: dict[str, Any]) -> bool:
        return not told_secrets and bool(summary_held(row, open_secrets, everyone))

    held = 0
    scenes: list[dict[str, Any]] = []
    for x in (told or {}).get("scenes") or []:
        row = x.get("summary")
        if row is None:
            continue
        if holds(row):
            held += 1
        else:
            scenes.append(row)
    story = (told or {}).get("story")
    if story is not None and holds(story):
        story, held = None, held + 1
    old = [t for t in threads if stale(t, last_turn) and (told_secrets or not kept(t))]
    if not scenes:
        return {"body": "", "turns": "", "made": "none", "cached": False, "held": held, "reason": "no_scenes",
                "stale": len(old)}
    newest: list[dict[str, Any]] = []
    size = 0
    for row in reversed(scenes):
        size += len(row["text"]) + 20
        if size > INPUT_CHARS and newest:
            break
        newest.insert(0, row)
    story = story if story is not None and newest[0]["first_turn"] > 0 else None  # only for turns the scenes leave out
    shown = [t for t in threads if (told_secrets or not kept(t)) and not stale(t, last_turn)]
    now = [f for f in facts if f["predicate"] in NOW_PREDICATES and not f.get("canon")
           and (told_secrets or not kept(f))][:NOW_MAX]
    first, last = (story or newest[0])["first_turn"], newest[-1]["last_turn"]
    title = f"## Chronicle (t{first}–{last})"
    opened = [_thread_line(t) for t in shown if t["status"] == "open"]
    tail = "\n\n## Open threads\n" + "\n".join(opened) if opened else ""
    budget = max(500, chars - len(tail) - len(title))
    user = _input(newest, story, shown, now, open_secrets, told_secrets)
    which = getattr(getattr(model, "__self__", None), "model", "") if model is not None else ""
    key = hashlib.sha256(f"{chars}|{told_secrets}|{which}|{user}".encode()).hexdigest()
    with _CACHE_LOCK:
        hit = _CACHE.get(key) if model is not None else None
        if hit is not None:
            _CACHE.move_to_end(key)
            return {**hit, "cached": True}

    def assembled() -> str:
        events = [f"- (t{r['first_turn']}–{r['last_turn']}) {r['text']}" for r in newest]
        if story is not None:
            events.insert(0, f"- (t{story['first_turn']}–{story['last_turn']}) {story['text']}")
        events += [_thread_line(t) for t in shown if t["status"] != "open"]
        nows = [f"- {_head(f)}: {_said(f)}" for f in now]
        return _cut_lines("\n".join(events) + ("\n\n## Now\n" + "\n".join(nows) if nows else ""), budget)

    made, body = "assembled", ""
    if model is not None:
        system = CHRONICLE_PROMPT.format(chars=budget, secrets=SECRETS_TOLD if told_secrets else SECRETS_KEPT)
        ask = user
        for _ in range(2):
            try:
                parsed, _, _ = metered(model, system, ask)
            except LLMError:
                break
            events, nows = str(parsed.get("events") or "").strip(), str(parsed.get("now") or "").strip()
            told_now = tells(events + "\n" + nows)
            if events and not told_now:
                made, body = "model", _cut_lines(events + (f"\n\n## Now\n{nows}" if nows else ""), budget)
                break
            if not told_now:  # an empty reply: the assembled text
                break
            ask = user + "\n\nYOUR LAST ANSWER TOLD THESE SECRETS; write it again without them:\n" + "\n".join(
                f"- {content(s)}" for s in told_now)
    out = {"body": f"{title}\n{body or assembled()}{tail}", "turns": f"{first}-{last}", "made": made, "cached": False,
           "held": held, "reason": "", "stale": len(old)}
    if made == "model":  # an assembled text costs nothing, and a failed call is tried again next time
        with _CACHE_LOCK:
            _CACHE[key] = out
            while len(_CACHE) > CACHE_MAX:
                _CACHE.popitem(last=False)
    return out


@dataclass(frozen=True)
class Ask:
    """What the owner asked for (PHASE-50 S7)."""
    sections: tuple[str, ...]
    chars: int
    secrets: bool
    model: bool

    @classmethod
    def of(cls, body: dict[str, Any]) -> "Ask":
        sections = tuple(dict.fromkeys(body.get("sections") or ()))
        if not sections or any(s not in KINDS for s in sections):
            raise ValueError(f"sections must be some of {', '.join(KINDS)}")
        chars = int(body.get("chars", 3000))
        if chars not in (3000, 6000):
            raise ValueError("chars must be 3000 or 6000")
        return cls(tuple(k for k in KINDS if k in sections), chars, bool(body.get("secrets", False)),
                   bool(body.get("model", True)))


def model_for(settings: Settings) -> Callable[..., tuple[Any, ...]] | None:
    """The extraction model and endpoint (PHASE-50 Q3), or None when none is configured."""
    if not (settings.llm_url and settings.llm_model):
        return None
    return ChatModel(settings.llm_url, settings.llm_model, settings.llm_api_key, settings.llm_timeout_s,
                     settings.llm_json_mode).complete_metered


def make(ask: Ask, view: dict[str, Any], told: dict[str, Any] | None, last_turn: int | None,
         model: Callable[..., tuple[Any, ...]] | None, today: str) -> dict[str, Any]:
    """The note: one block holding every part asked for that has something to say, and what each part was made of."""
    facts = view.get("facts") or []
    parts: list[str] = []
    info = []
    for kind in ask.sections:
        if kind == "chronicle":
            c = chronicle(told, view.get("threads") or [], facts, view.get("secrets") or [], ask.chars,
                          model if ask.model else None, ask.secrets, last_turn)
            body = c["body"]
            info.append({"kind": kind, "made": c["made"], "cached": c["cached"], "held": c["held"],
                         "reason": c["reason"], "turns": c["turns"], "chars": len(body), "stale": c["stale"]})
        else:
            lines = changed_lines(facts, ask.secrets) if kind == "changed" else address_lines(facts, ask.secrets, frozenset(view.get("excluded") or ()))
            body = f"{CHANGED_HEAD if kind == 'changed' else ADDRESS_HEAD}\n" + "\n".join(lines) if lines else ""
            info.append({"kind": kind, "made": "facts", "cached": False, "held": 0, "reason": "" if lines else "none",
                         "turns": str(last_turn or 0), "lines": len(lines), "chars": len(body)})
        if body:
            parts.append(body)
    text = ""
    if parts:
        text = wrap("\n\n".join([HEADER.format(turn=last_turn or 0), *parts]), last_turn, today)
    return {"text": text, "chars": len(text), "sections": info, "last_turn": last_turn}
