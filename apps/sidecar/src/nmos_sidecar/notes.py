"""Notes for the author's note (PHASE-50): sections the owner pastes into a chat's author's note, made on request.

Three kinds: the chronicle (the story's events, how they went and ended, from the scene summaries and the threads; one
model call, with an assembled fallback), what changed from the setting (canon values a story fact now supersedes) and
address and standing (each pair's relationship, role, feeling and form of address). Each is written between two marker
lines. The author's note is canon (ADR 0045), so the canon never reads a marked block: the plugin removes them before
the hash, and `canonfacts.process` again before a read (an older plugin sends them whole).

Nothing is stored and no packet reads these sections: they are views of memory, made when asked.
"""

from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .entities import norm
from .facts import symmetric
from .inspector import _named, pairs
from .noteblocks import KINDS, LABELS, strip_blocks, wrap  # noqa: F401  (the API's names for them)
from .predicates import HOLDER_PER_ITEM, REGISTRY
from .config import Settings
from .llm import ChatModel, LLMError, metered
from .summaries import content, held as summary_held, leaks

PAIRS_MAX = 30  # address lines at most
PAIRWISE = frozenset({"relationship", "role_toward", "feels_toward", "addresses"})
# A canon value a story fact can replace: single-valued predicates and an item's holder (PHASE-50 S3). A multi-valued
# one accumulates, so NMOS cannot tell a change from an addition there.
CHANGEABLE = frozenset(p for p, d in REGISTRY.items() if d.cardinality == "single") | HOLDER_PER_ITEM
WORDS = {
    "ko": {"located_in": "위치", "has_status": "상태", "identity": "정체", "relationship": "관계", "role_toward": "역할",
           "feels_toward": "감정", "addresses": "호칭", "possesses": "소지자", "destroyed": "소멸",
           "setting": "설정", "now": "지금", "not": "아님:", "secret": "비밀: {who}는 모름", "fixed": "직접 고침"},
    "en": {"located_in": "location", "has_status": "status", "identity": "identity", "relationship": "relationship",
           "role_toward": "role", "feels_toward": "feeling", "addresses": "calls", "possesses": "held by",
           "destroyed": "destroyed", "setting": "setting", "now": "now", "not": "not",
           "secret": "secret: {who} does not know", "fixed": "fixed by the owner"},
}


def _w(lang: str, key: str) -> str:
    return WORDS["en" if lang == "en" else "ko"].get(key, key.replace("_", " "))


def kept(x: dict[str, Any]) -> bool:
    """Kept from someone. The note is read in every scene, so any limited fact counts (PHASE-50 S4)."""
    return x.get("knowledge") == "limited" or bool(x.get("hidden_from"))


def _secret_mark(x: dict[str, Any], lang: str) -> str:
    return f" ({_w(lang, 'secret').format(who=', '.join(x.get('hidden_from') or []) or '?')})"


def _said(e: dict[str, Any], lang: str) -> str:
    """What a statement says in its slot: an item's holder, else its value or object."""
    said = e.get("subject") if e["predicate"] in HOLDER_PER_ITEM else (e.get("value") or e.get("object") or "")
    return f"{_w(lang, 'not')} {said}" if e.get("polarity") == "negative" else str(said)


def _head(f: dict[str, Any], lang: str) -> str:
    if f["predicate"] in HOLDER_PER_ITEM:
        return f"{f.get('object')} {_w(lang, f['predicate'])}"
    if f["predicate"] in PAIRWISE and f.get("object"):
        return f"{_named(f, 'subject')} → {_named(f, 'object')} {_w(lang, f['predicate'])}"
    return f"{_named(f, 'subject')} {_w(lang, f['predicate'])}"


def changed_lines(facts: list[dict[str, Any]], lang: str, secrets: bool = False) -> list[str]:
    """Each canon value a current story fact replaced or ended (a canon entry of its history), newest first. With
    `secrets` off, nothing kept from someone."""
    out: list[str] = []
    seen: set[tuple[Any, ...]] = set()
    for f in facts:
        if f.get("canon") or f["predicate"] not in CHANGEABLE or (kept(f) and not secrets):
            continue
        for h in f.get("history") or ():
            if not h.get("canon") or h.get("outcome") not in ("superseded", "ended") or (kept(h) and not secrets):
                continue
            old, new = _said(h, lang), _said(f, lang)
            key = (f["predicate"], h.get("subject"), h.get("object"), old, new)
            if old == new or key in seen:
                continue
            seen.add(key)
            line = f"- {_head(f, lang)}: {_w(lang, 'setting')} {old} → {_w(lang, 'now')} {new} (t{f.get('turn')})"
            if f.get("repair"):
                line += f" ({_w(lang, 'fixed')})"
            out.append(line + (_secret_mark(f, lang) if kept(f) else ""))
    return out


def address_lines(facts: list[dict[str, Any]], lang: str, secrets: bool = False) -> list[str]:
    """One line per pair (`inspector.pairs`, newest first): the relationship, then each direction's role, feeling and
    form of address. With `secrets` off, nothing kept from someone."""
    out = []
    for p in pairs([f for f in facts if secrets or not kept(f)])[:PAIRS_MAX]:
        bits = []
        for f in p["relationship"]:
            both = symmetric(f.get("value")) and len(p["relationship"]) == 1
            who = "" if both else f"{_named(f, 'subject')}→{_named(f, 'object')} "
            bits.append(f"{who}{_w(lang, 'relationship')} {f.get('value')}" + (_secret_mark(f, lang) if kept(f) else ""))
        for k, pred in (("role", "role_toward"), ("feels", "feels_toward"), ("speech", "addresses")):
            for f in p[k]:
                value = f'"{f.get("value")}"' if pred == "addresses" else f.get("value")
                bits.append(f"{_named(f, 'subject')}→{_named(f, 'object')} {_w(lang, pred)} {value}"
                            + (_secret_mark(f, lang) if kept(f) else ""))
        if bits:
            out.append(f"- {' ↔ '.join(sorted(p['names'].values()))}: " + " · ".join(bits))
    return out


INPUT_CHARS = 40_000  # the newest scene summaries the chronicle reads (PHASE-50 Q2 (a)); older turns by the story so far
NOW_MAX = 30  # "now" facts in the chronicle's input
NOW_PREDICATES = frozenset({"located_in", "has_status"})
CACHE_MAX = 64
_CACHE: OrderedDict[str, dict[str, Any]] = OrderedDict()  # model-written chronicles only, by their whole input
_CACHE_LOCK = threading.Lock()  # requests run in the server's thread pool
THREAD_WORDS = {"ko": {"promise": "약속", "goal": "목표", "question": "질문", "threat": "위협", "debt": "빚",
                       "since": "t{t}부터", "events": "사건", "now": "지금", "open": "열린 일"},
                "en": {"promise": "promise", "goal": "goal", "question": "question", "threat": "threat", "debt": "debt",
                       "since": "since t{t}", "events": "Events", "now": "Now", "open": "Open threads"}}

CHRONICLE_PROMPT = """You write a chronicle of a role-play chat, for its author's note: the user pastes it so that the
model writing the story keeps what happened in mind. You get SCENES (summaries in order, each with its turns), maybe
the STORY SO FAR (it covers turns before the first scene given), THREADS (promises, goals, questions, threats and
debts, each with its state and, when it ended, its outcome) and NOW (where characters are and how they are).

Write two parts in the language of the chat:
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
SECRETS are listed: you may write them, each marked with who does not know it, like "(Kaito does not know)", in the
language of the chat.
"""


def clear_cache() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()


def _tw(lang: str, key: str) -> str:
    return THREAD_WORDS["en" if lang == "en" else "ko"].get(key, key)


def _cut_lines(text: str, cap: int) -> str:
    """At most `cap` characters, at a line end when one is in the last third."""
    text = text.strip()
    if len(text) <= cap:
        return text
    head = text[:cap]
    end = head.rfind("\n")
    return head[:end].rstrip() if end >= cap * 2 // 3 else head.rstrip()


def _thread_line(t: dict[str, Any], lang: str) -> str:
    who = f"{t['by']} → {t['to']}" if t.get("to") else str(t["by"])
    if t["status"] == "open":
        return f"- {who}: {t['text']} ({_tw(lang, t['kind'])}, {_tw(lang, 'since').format(t=t.get('turn'))})"
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
    lines += ["THREADS:"] + [_thread_line(t, "en") for t in threads] + [""]
    lines += ["NOW:"] + [f"- {_head(f, 'en')}: {_said(f, 'en')}" for f in now]
    return "\n".join(lines)


def chronicle(told: dict[str, Any] | None, threads: list[dict[str, Any]], facts: list[dict[str, Any]],
              secrets: list[dict[str, Any]], chars: int, lang: str, model: Callable[..., tuple[Any, ...]] | None,
              told_secrets: bool = False) -> dict[str, Any]:
    """The chronicle's body, without its markers (PHASE-50 S2): Events and Now from the model, or assembled from the
    summaries when there is no model or its replies fail; Open threads always from the stored threads.

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
    if not scenes:
        return {"body": "", "turns": "", "made": "none", "cached": False, "held": held, "reason": "no_scenes"}
    newest: list[dict[str, Any]] = []
    size = 0
    for row in reversed(scenes):
        size += len(row["text"]) + 20
        if size > INPUT_CHARS and newest:
            break
        newest.insert(0, row)
    story = story if story is not None and newest[0]["first_turn"] > 0 else None  # only for turns the scenes leave out
    shown = [t for t in threads if told_secrets or not kept(t)]
    now = [f for f in facts if f["predicate"] in NOW_PREDICATES and not f.get("canon")
           and (told_secrets or not kept(f))][:NOW_MAX]
    turns = f"{(story or newest[0])['first_turn']}-{newest[-1]['last_turn']}"
    opened = [_thread_line(t, lang) for t in shown if t["status"] == "open"]
    tail = f"\n\n## {_tw(lang, 'open')}\n" + "\n".join(opened) if opened else ""
    budget = max(500, chars - len(tail))
    user = _input(newest, story, shown, now, open_secrets, told_secrets)
    which = getattr(getattr(model, "__self__", None), "model", "") if model is not None else ""
    key = hashlib.sha256(f"{lang}|{chars}|{told_secrets}|{which}|{user}".encode()).hexdigest()
    with _CACHE_LOCK:
        hit = _CACHE.get(key) if model is not None else None
        if hit is not None:
            _CACHE.move_to_end(key)
            return {**hit, "cached": True}

    def assembled() -> str:
        events = [f"- (t{r['first_turn']}–{r['last_turn']}) {r['text']}" for r in newest]
        if story is not None:
            events.insert(0, f"- (t{story['first_turn']}–{story['last_turn']}) {story['text']}")
        events += [_thread_line(t, lang) for t in shown if t["status"] != "open"]
        nows = [f"- {_head(f, lang)}: {_said(f, lang)}" for f in now]
        body = f"## {_tw(lang, 'events')}\n" + "\n".join(events)
        return _cut_lines(body + (f"\n\n## {_tw(lang, 'now')}\n" + "\n".join(nows) if nows else ""), budget)

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
                text = f"## {_tw(lang, 'events')}\n{events}" + (f"\n\n## {_tw(lang, 'now')}\n{nows}" if nows else "")
                made, body = "model", _cut_lines(text, budget)
                break
            if not told_now:  # an empty reply: the assembled text
                break
            ask = user + "\n\nYOUR LAST ANSWER TOLD THESE SECRETS; write it again without them:\n" + "\n".join(
                f"- {content(s)}" for s in told_now)
    out = {"body": (body or assembled()) + tail, "turns": turns, "made": made, "cached": False, "held": held,
           "reason": ""}
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
    lang: str

    @classmethod
    def of(cls, body: dict[str, Any]) -> "Ask":
        sections = tuple(dict.fromkeys(body.get("sections") or ()))
        if not sections or any(s not in KINDS for s in sections):
            raise ValueError(f"sections must be some of {', '.join(KINDS)}")
        chars = int(body.get("chars", 3000))
        if chars not in (3000, 6000):
            raise ValueError("chars must be 3000 or 6000")
        return cls(sections, chars, bool(body.get("secrets", False)), bool(body.get("model", True)),
                   "en" if body.get("lang") == "en" else "ko")


def model_for(settings: Settings) -> Callable[..., tuple[Any, ...]] | None:
    """The extraction model and endpoint (PHASE-50 Q3), or None when none is configured."""
    if not (settings.llm_url and settings.llm_model):
        return None
    return ChatModel(settings.llm_url, settings.llm_model, settings.llm_api_key, settings.llm_timeout_s,
                     settings.llm_json_mode).complete_metered


def make(ask: Ask, view: dict[str, Any], told: dict[str, Any] | None, last_turn: int | None,
         model: Callable[..., tuple[Any, ...]] | None, today: str) -> dict[str, Any]:
    """Every section asked for, each between its markers; one with nothing to say is empty, with its reason."""
    facts = view.get("facts") or []
    out = []
    for kind in ask.sections:
        if kind == "chronicle":
            c = chronicle(told, view.get("threads") or [], facts, view.get("secrets") or [], ask.chars, ask.lang,
                          model if ask.model else None, ask.secrets)
            body, turns, made, cached, held, reason = (c["body"], c["turns"], c["made"], c["cached"], c["held"],
                                                       c["reason"])
        else:
            lines = (changed_lines if kind == "changed" else address_lines)(facts, ask.lang, ask.secrets)
            body, turns, made, cached, held = "\n".join(lines), str(last_turn or 0), "facts", False, 0
            reason = "" if lines else "none"
        out.append({"kind": kind, "text": wrap(kind, body, turns, ask.lang, today) if body else "", "turns": turns,
                    "made": made, "cached": cached, "held": held, "reason": reason, "chars": len(body)})
    return {"sections": out, "last_turn": last_turn}
