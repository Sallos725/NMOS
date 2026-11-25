"""A note for the author's note (PHASE-50): one block the owner pastes into a chat's author's note, made on request.

Its frame (headings, the lines NMOS assembles) is English Markdown (amendment 2: the model reads the note, not a
person), with names, titles and quoted words as the chat writes them; what a model writes for it is in the chat's own
language by default (`language="chat"`: a Korean chat gets a Korean chronicle, so the secret check compares like with
like) or in English on request (`"en"`). It holds up to four parts the owner picks: what diverged from the setting
(PHASE-53, `divergence`: one checked model call, with Phase 50's changed lines as its fallback), the chronicle (the
story's events, how they went and ended, from the scene summaries and the threads; one model call, with an assembled
fallback), what changed from the setting (canon values a story fact now supersedes) and address and standing (each
pair's relationship, role, feeling and form of address). The block sits between two marker lines: the author's note is
canon (ADR 0045), so the canon never reads it (`noteblocks`).

A secret kept from someone is checked in every line the note says, the model's and the assembled ones (`tells`, at
LEAK_NEAR). That check compares letters, so a model reply in another script than a secret (an English chronicle of a
Korean secret) is also put to `semantic_leaks` when one is given (`embedding_leak_checker`, `model_leak_checker`); a
checker that fails counts as a leak.

Nothing is stored and no packet reads the note: it is a view of memory, made when asked.
"""

from __future__ import annotations

import hashlib
import math
import re
import threading
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from . import calls, divergence
from .config import Settings
from .entities import norm
from .facts import symmetric
from .inspector import _named, pairs, stale
from .llm import ChatModel, LLMError, metered
from .noteblocks import strip_blocks, wrap  # noqa: F401  (the API's names for them)
from .predicates import HOLDER_PER_ITEM, REGISTRY, address_label
from .runtime import NOTES_PROMPT_KEY
from .summaries import content, held as summary_held, leaks, unnamed

LeakCheck = Callable[[str, list[dict[str, Any]]], list[dict[str, Any]]]  # (text, open secrets) → the secrets it tells
LANGUAGES = ("chat", "en")  # what a model writes the note's parts in: the chat's own language, or English
_HANGUL = re.compile(r"[\uac00-\ud7a3\u1100-\u11ff\u3130-\u318f]")
_LATIN = re.compile(r"[A-Za-z]")

KINDS = ("diverged", "chronicle", "changed", "address", "custom")  # the parts the owner can pick, in the note's order
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
          "What the story has established so far. The latest messages take precedence over it.\n"
          "The character card and lorebook were written before the story began: where they disagree with this note,"
          " this note is true now.")
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
        cond = f" [{label}]" if (label := address_label(f)) else ""
        return f"{_named(f, 'subject')} → {_named(f, 'object')} — {_w(f['predicate'])}{cond}"
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
                cond = f" [{label}]" if (pred == "addresses" and (label := address_label(f))) else ""
                bits.append(f"{_named(f, 'subject')}→{_named(f, 'object')} {_w(pred)}{cond} {value}"
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

Write two parts {language}; keep names, titles, places and quoted words exactly as
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
# How each prompt names the language to write in. English keeps the prompts as they were before `language` existed.
CHRONICLE_LANGUAGE = {"en": "in English, whatever the language of the chat",
                      "ko": "in Korean, the language of the chat"}
CUSTOM_LANGUAGE = {"en": "English,", "ko": "Korean, the language of the chat,"}


def script(text: str) -> str:
    """"ko" when most of a text's letters are Hangul, else "en"."""
    hangul, latin = len(_HANGUL.findall(text)), len(_LATIN.findall(text))
    return "ko" if hangul and hangul >= latin else "en"


def chat_language(scenes: list[dict[str, Any]], story: dict[str, Any] | None, threads: list[dict[str, Any]],
                  now: list[dict[str, Any]]) -> str:
    """The language a chat is written in, from its scene summaries (written in the language of the chat), or from its
    threads and facts while it has none: "ko" or "en"."""
    texts = [r["text"] for r in scenes] + ([story["text"]] if story is not None else [])
    if not texts:
        texts = [str(t.get("text") or "") for t in threads] + [str(_said(f)) for f in now]
    return script("\n".join(texts))


def language_of(language: str, scenes: list[dict[str, Any]], story: dict[str, Any] | None,
                threads: list[dict[str, Any]], now: list[dict[str, Any]]) -> str:
    if language not in LANGUAGES:
        raise ValueError(f"language must be one of {', '.join(LANGUAGES)}")
    return "en" if language == "en" else chat_language(scenes, story, threads, now)


# --- secrets said in other words or another language ------------------------------------------------------------------

LEAK_THRESHOLD = 0.62  # cosine similarity of a line of the note and a secret's content
UNITS_MAX = 40  # lines and sentences of one text embedded for the check


def _units(text: str) -> list[str]:
    """The lines and sentences of a text, list marks left out."""
    parts = re.split(r"(?<=[.!?。！？])\s+|\n+", text)
    return [u for u in (re.sub(r"^\s*(?:[-*#>]+\s*)+", "", p).strip() for p in parts) if len(u) >= 4]


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a, norm_b = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0


def embedding_leak_checker(embedder: Any, threshold: float = LEAK_THRESHOLD, timeout_s: float = 30) -> LeakCheck:
    """A `semantic_leaks` check by meaning: a secret is told when a line or sentence of the text embeds within
    `threshold` (cosine) of its content, the names of its holders and of those it is kept from left out of both (as
    `summaries.leak_score` does). One embedding request per text (`embedder.embed`); an error is the caller's to
    handle (`tells` counts it as a leak)."""

    def check(text: str, secrets: list[dict[str, Any]]) -> list[dict[str, Any]]:
        units = _units(text)[:UNITS_MAX]
        if not units or not secrets:
            return []
        names = sorted({n for s in secrets for n in (*s.get("holders", []), *s.get("open", []))})
        bare = [unnamed(content(s), names).strip() or content(s) for s in secrets]
        vectors = embedder.embed(bare + [unnamed(u, names).strip() or u for u in units], timeout_s=timeout_s)
        told, said = vectors[:len(secrets)], vectors[len(secrets):]
        return [s for s, v in zip(secrets, told) if any(_cosine(v, u) >= threshold for u in said)]

    return check


LEAK_CHECK_PROMPT = """You check a text written for the author's note of a role-play chat against SECRETS, each kept
from some characters. A secret is told when the text says its content, in any language or in other words, or hints at
it so that a reader could tell what it is. Names alone do not tell a secret.

Answer with JSON only: {"told": [the numbers of the secrets the text tells]}"""


def model_leak_checker(model: Callable[..., tuple[Any, ...]]) -> LeakCheck:
    """A `semantic_leaks` check by one model call per text, for an install without an embedder. A reply that is not a
    list of the secrets' numbers raises (`tells` counts it as a leak)."""

    def check(text: str, secrets: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not secrets or not text.strip():
            return []
        user = ("SECRETS:\n" + "\n".join(f"{i}. {content(s)}" for i, s in enumerate(secrets, 1))
                + "\n\nTEXT:\n" + text)
        parsed, _, _ = metered(model, LEAK_CHECK_PROMPT, user)
        told = parsed.get("told") if isinstance(parsed, dict) else None
        if not isinstance(told, list):
            raise LLMError("leak check: no list of secrets")
        return [secrets[i - 1] for i in dict.fromkeys(told) if isinstance(i, int) and 1 <= i <= len(secrets)]

    return check


def clear_cache() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()
    divergence.clear_cache()


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
    if scenes:
        lines += ["SCENES:"] + [f"[turns {s['first_turn']}–{s['last_turn']}] {s['text']}" for s in scenes] + [""]
    else:  # the first turns, a chat without a summarizer, or every summary held for a secret
        lines += ["SCENES: (none to read; THREADS and NOW say where the story stands)", ""]
    lines += ["THREADS:"] + [_thread_line(t) for t in threads] + [""]
    lines += ["NOW:"] + [f"- {_head(f)}: {_said(f)}" for f in now]
    return "\n".join(lines)


def _story(told: dict[str, Any] | None, threads: list[dict[str, Any]], facts: list[dict[str, Any]],
           secrets: list[dict[str, Any]], told_secrets: bool, last_turn: int | None, language: str = "chat",
           semantic_leaks: LeakCheck | None = None) -> dict[str, Any]:
    """The chronicle's story input (PHASE-50 S2), which the custom part reads too (PHASE-56 C4): the newest scene
    summaries in INPUT_CHARS, the story so far for the turns they leave out, the threads shown, the NOW facts, how many
    summaries were held for a secret, the stale threads, the language a model writes in ("ko" or "en", `language_of`)
    and `tells`, the leak check of a text. `newest` is empty when there is no scene summary to read; `early` says there
    is still something to tell then (a thread shown or a NOW fact: the first turns, PHASE-50 C2).

    `tells` compares letters (`summaries.leaks`, at LEAK_NEAR), which says nothing about a secret written in another
    script. So a model's reply (`semantic=True`) is also put to `semantic_leaks`, when given, for each secret written
    mostly in another script than the reply (a Korean secret, an English chronicle); a check that raises counts every
    such secret as told, so the reply is asked again and then left out, never let through unchecked."""
    open_secrets = [s for s in secrets if s.get("open")]
    everyone = frozenset(norm(n) for s in open_secrets for n in s["open"])

    def tells(text: str, semantic: bool = True) -> list[dict[str, Any]]:
        if told_secrets:
            return []
        found = leaks(text, open_secrets, everyone)
        if not semantic or semantic_leaks is None or not text.strip():
            return found
        written = script(text)
        other = [s for s in open_secrets if s not in found and script(content(s)) != written]
        if not other:
            return found
        try:
            said = semantic_leaks(text, other)
        except Exception:  # noqa: BLE001 (an embedder or model that fails: count it as told, fail closed)
            said = other
        return found + [s for s in other if s in said]

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
    newest: list[dict[str, Any]] = []
    size = 0
    for row in reversed(scenes):
        size += len(row["text"]) + 20
        if size > INPUT_CHARS and newest:
            break
        newest.insert(0, row)
    # the story so far only for the turns the scenes leave out
    story = story if story is not None and newest and newest[0]["first_turn"] > 0 else None
    shown = [t for t in threads if (told_secrets or not kept(t)) and not stale(t, last_turn)]
    now = [f for f in facts if f["predicate"] in NOW_PREDICATES and not f.get("canon")
           and (told_secrets or not kept(f))][:NOW_MAX]
    if newest:
        first, last = (story or newest[0])["first_turn"], newest[-1]["last_turn"]
    else:  # the first turns: from the threads and facts said so far
        turns = [x.get("turn") for x in (*shown, *now) if isinstance(x.get("turn"), int) and x["turn"] >= 0]
        last = last_turn if last_turn is not None else max(turns, default=0)
        first = min(turns, default=last)
    return {"open_secrets": open_secrets, "tells": tells, "held": held, "old": old, "newest": newest, "story": story,
            "shown": shown, "now": now, "early": not newest and bool(shown or now), "first": first, "last": last,
            "language": language_of(language, newest, story, shown, now)}


THREADS_MAX = 15  # open threads in the chronicle's list at most, newest first
THREADS_SHARE = 0.25  # of the part's characters, at most this much for that list


def _open_threads(shown: list[dict[str, Any]], tells: Callable[..., list[dict[str, Any]]], chars: int) -> str:
    """The chronicle's "Open threads" list: the newest open threads (THREADS_MAX) in at most THREADS_SHARE of the
    part, in the store's order, with how many more there are; none that tells a secret (`tells`) and none counted."""
    lines = [(t, _thread_line(t)) for t in shown if t["status"] == "open"]
    lines = [(t, line) for t, line in lines if not tells(line, semantic=False)]
    if not lines:
        return ""
    cap = int(chars * THREADS_SHARE)
    newest_first = sorted(range(len(lines)), key=lambda i: (lines[i][0].get("turn") or -1, i), reverse=True)
    keep: set[int] = set()
    size = 0
    for i in newest_first:
        if len(keep) >= THREADS_MAX or (keep and size + len(lines[i][1]) + 1 > cap):
            break
        keep.add(i)
        size += len(lines[i][1]) + 1
    out = [line for i, (_, line) in enumerate(lines) if i in keep]
    if len(keep) < len(lines):
        out.append(f"- (+{len(lines) - len(keep)} more open threads)")
    return "\n\n## Open threads\n" + "\n".join(out)


def chronicle(told: dict[str, Any] | None, threads: list[dict[str, Any]], facts: list[dict[str, Any]],
              secrets: list[dict[str, Any]], chars: int, model: Callable[..., tuple[Any, ...]] | None,
              told_secrets: bool = False, last_turn: int | None = None, language: str = "chat",
              semantic_leaks: LeakCheck | None = None, finale: str | None = None) -> dict[str, Any]:
    """The chronicle's Markdown (PHASE-50 S2): Events and Now from the model, or assembled from the summaries when there
    is no model or its replies fail; Open threads always from the stored threads (the newest THREADS_MAX, in at most
    THREADS_SHARE of the part, so they never crowd out the story). An open thread not said again for longer than its
    horizon allows (`inspector.stale`, the Inspector's "needs a look") is left out of both, and counted (amendment 3):
    the note is read every turn, and a lasting thread (PHASE-51) never goes stale.

    Before the first scene summary (the first turns), the chronicle is made from the threads and NOW facts said so far,
    when there are any; with neither it is left out (`no_scenes`). The model writes in the chat's language by default
    (`language="chat"`), or in English (`"en"`).

    With `told_secrets` off, nothing kept from someone goes in. A scene summary or story is left out when the packet
    would hold it with every character a secret is kept from in the scene (`summaries.held`: it repeats a secret at
    LEAK_NEAR, or was written before a secret it should have been told about; the note is read in every scene), a
    reply is refused when it repeats one (`tells`: at LEAK_NEAR, and by `semantic_leaks` across scripts; asked once
    more, then the assembled text), and an assembled line or an open thread that repeats one is left out."""
    s = _story(told, threads, facts, secrets, told_secrets, last_turn, language, semantic_leaks)
    open_secrets, held, old, newest, story, shown, now = (s["open_secrets"], s["held"], s["old"], s["newest"],
                                                          s["story"], s["shown"], s["now"])
    tells, lang = s["tells"], s["language"]
    if not newest and not s["early"]:
        return {"body": "", "turns": "", "made": "none", "cached": False, "held": held, "reason": "no_scenes",
                "stale": len(old)}
    first, last = s["first"], s["last"]
    title = f"## Chronicle (t{first}–{last})"
    tail = _open_threads(shown, tells, chars)
    budget = max(500, chars - len(tail) - len(title))
    user = _input(newest, story, shown, now, open_secrets, told_secrets)
    which = getattr(getattr(model, "__self__", None), "model", "") if model is not None else ""
    checked = "semantic" if semantic_leaks is not None else ""
    # PHASE-67: `finale`, the revision of the provisional reply the view read (`view["open_turn"]`): a reroll is a new key
    key = hashlib.sha256(f"{chars}|{told_secrets}|{which}|{lang}|{checked}|{user}"
                         f"{'|finale:' + finale if finale else ''}".encode()).hexdigest()
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
        # each line on its own: one that repeats a secret is left out, the rest stay
        events = [line for line in events if not tells(line, semantic=False)]
        nows = [line for line in nows if not tells(line, semantic=False)]
        text = "\n".join(events) + ("\n\n## Now\n" + "\n".join(nows) if nows else "")
        return _cut_lines(text, budget)

    made, body = "assembled", ""
    if model is not None:
        system = CHRONICLE_PROMPT.format(chars=budget, secrets=SECRETS_TOLD if told_secrets else SECRETS_KEPT,
                                         language=CHRONICLE_LANGUAGE[lang])
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
    body = body or assembled()
    if not body and not tail:  # every line held for a secret: nothing to tell
        return {"body": "", "turns": f"{first}-{last}", "made": "none", "cached": False, "held": held,
                "reason": "none", "stale": len(old)}
    out = {"body": f"{title}\n{body}{tail}" if body else f"{title}{tail}", "turns": f"{first}-{last}", "made": made,
           "cached": False, "held": held, "reason": "", "stale": len(old)}
    if made == "model":  # an assembled text costs nothing, and a failed call is tried again next time
        with _CACHE_LOCK:
            _CACHE[key] = out
            while len(_CACHE) > CACHE_MAX:
                _CACHE.popitem(last=False)
    return out


PROMPT_MAX = 4_000  # characters of the owner's prompt for the custom part (PHASE-56 C1)
PROMPT_KEY = NOTES_PROMPT_KEY  # its app_config row: one prompt for every chat, in a full archive (PHASE-56 C2, amendment 1)
CUSTOM_HEAD = "## Custom (owner's prompt)"
CUSTOM_PROMPT = """You write one part of the author's note of a role-play chat: the user pastes the note so that the
model writing the story keeps it in mind. You get SCENES (summaries in order, each with its turns), maybe the STORY SO
FAR (it covers turns before the first scene given), THREADS (promises, goals, questions, threats and debts, each with
its state and, when it ended, its outcome) and NOW (where characters are and how they are).{setting}

The user's instruction for this part, between the two lines of equals signs:
==========
{prompt}
==========

Write what the instruction asks, from the input only: no invented events, no guesses. Keep names, titles, places and
quoted words exactly as the input writes them. Write in {write_in} unless the instruction explicitly names another
language to write in: the language the instruction itself is written in is not such a request. You may use "###"
headings and "- " lists; do not repeat the part's heading. At most {chars} characters.
{secrets}
Answer with JSON only: {{"text": "..."}}"""
CUSTOM_SETTING = """
You also get the SETTING: the character card, the persona, the author's note and lorebook entries, each under its key.
It was written before the story began; where the story has moved on, the story is true now."""


def custom(prompt: str, told: dict[str, Any] | None, threads: list[dict[str, Any]], facts: list[dict[str, Any]],
           secrets: list[dict[str, Any]], chars: int, model: Callable[..., tuple[Any, ...]] | None,
           told_secrets: bool = False, last_turn: int | None = None, setting: list[dict[str, Any]] | None = None,
           entities: list[dict[str, Any]] | None = None, excluded: frozenset[str] = frozenset(),
           language: str = "chat", semantic_leaks: LeakCheck | None = None,
           finale: str | None = None) -> dict[str, Any]:
    """The custom part's Markdown (PHASE-56): the owner's prompt in a fixed frame over the chronicle's story input and,
    when `setting` (the manifest in force) is given, the setting's side as PHASE-53 S3 picks it. One call, asked again
    once when the reply is not JSON with a string `text` or (secrets off) when it repeats an open secret at LEAK_NEAR;
    then the part is left out, with its reason: there is no fallback. An answer, an empty one included, is cached by
    the whole input; a failed or held part is not, so the next request calls again. As the chronicle, it is made from
    the threads and NOW facts before the first scene summary, and written in the chat's language unless `language` is
    "en" or the owner's prompt names another one."""
    s = _story(told, threads, facts, secrets, told_secrets, last_turn, language, semantic_leaks)
    open_secrets, newest, story, tells = s["open_secrets"], s["newest"], s["story"], s["tells"]
    base = {"body": "", "turns": "", "made": "none", "cached": False, "held": s["held"], "reason": "",
            "stale": len(s["old"])}
    if not newest and not s["early"]:
        return {**base, "reason": "no_scenes"}
    base["turns"] = f"{s['first']}-{s['last']}"
    user = _input(newest, story, s["shown"], s["now"], open_secrets, told_secrets)
    if setting is not None:
        shown_facts = [f for f in facts if told_secrets or not kept(f)]  # as PHASE-53 ranks entries
        given, left = divergence.canon_input(setting, entities or [], shown_facts, user, excluded)
        base |= {"entries": sum(g["key"].startswith("lore:") for g in given), "left_out": left}
        lines = ["SETTING:"]
        for g in given:
            lines += [f"[key: {g['key']}] ({g['label']})", g["text"], ""]
        user = "\n".join(lines) + "\n" + user
    if model is None:
        return {**base, "reason": "no_model"}
    budget = max(500, chars - len(CUSTOM_HEAD) - 1)
    system = CUSTOM_PROMPT.format(setting=CUSTOM_SETTING if setting is not None else "", prompt=prompt.strip(),
                                  chars=budget, secrets=SECRETS_TOLD if told_secrets else SECRETS_KEPT,
                                  write_in=CUSTOM_LANGUAGE[s["language"]])
    which = getattr(getattr(model, "__self__", None), "model", "")
    checked = "semantic" if semantic_leaks is not None else ""
    key = hashlib.sha256(f"custom|{chars}|{told_secrets}|{which}|{checked}|{system}|{user}"
                         f"{'|finale:' + finale if finale else ''}".encode()).hexdigest()  # PHASE-67, as the chronicle
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
        if hit is not None:
            _CACHE.move_to_end(key)
            return {**hit, "cached": True}
    ask, reason = user, "failed"
    for _ in range(2):
        try:
            parsed, _, _ = metered(model, system, ask)
        except LLMError:
            continue
        text = parsed.get("text") if isinstance(parsed, dict) else None
        if not isinstance(text, str):
            continue
        told_now = tells(text)
        if told_now:
            reason = "held"
            ask = user + "\n\nYOUR LAST ANSWER TOLD THESE SECRETS; write it again without them:\n" + "\n".join(
                f"- {content(x)}" for x in told_now)
            continue
        body = _cut_lines(text, budget)
        out = {**base, "made": "model", "reason": "" if body else "none",
               "body": f"{CUSTOM_HEAD}\n{body}" if body else ""}
        with _CACHE_LOCK:
            _CACHE[key] = out
            while len(_CACHE) > CACHE_MAX:
                _CACHE.popitem(last=False)
        return out
    return {**base, "reason": reason}


@dataclass(frozen=True)
class Ask:
    """What the owner asked for (PHASE-50 S7)."""
    sections: tuple[str, ...]
    chars: int
    secrets: bool
    model: bool
    custom_prompt: str = ""  # PHASE-56: only when `custom` is asked for
    custom_setting: bool = False
    language: str = "chat"  # what the model writes in: the chat's language, or "en" (an older plugin sends none)

    @classmethod
    def of(cls, body: dict[str, Any]) -> "Ask":
        sections = tuple(dict.fromkeys(body.get("sections") or ()))
        if not sections or any(s not in KINDS for s in sections):
            raise ValueError(f"sections must be some of {', '.join(KINDS)}")
        if "diverged" in sections:  # its fallback is the same lines; an older plugin still asks for `changed` alone
            sections = tuple(s for s in sections if s != "changed")
        chars = int(body.get("chars", 3000))
        if chars not in (3000, 6000):
            raise ValueError("chars must be 3000 or 6000")
        prompt, setting = "", False
        if "custom" in sections:
            prompt = body.get("custom_prompt")
            if not isinstance(prompt, str) or not prompt.strip() or len(prompt.strip()) > PROMPT_MAX:
                raise ValueError(f"custom_prompt must be text of 1 to {PROMPT_MAX} characters")
            prompt, setting = prompt.strip(), bool(body.get("custom_setting", False))
        language = body.get("language", "chat")
        if language not in LANGUAGES:
            raise ValueError(f"language must be one of {', '.join(LANGUAGES)}")
        return cls(tuple(k for k in KINDS if k in sections), chars, bool(body.get("secrets", False)),
                   bool(body.get("model", True)), prompt, setting, language)


def model_for(settings: Settings, *, log_to: str | None = None,
              conversation_id: UUID | None = None) -> Callable[..., tuple[Any, ...]] | None:
    """The extraction model and endpoint (PHASE-50 Q3), or None when none is configured. With `log_to` (a database
    URL) each call is logged there as a `note` of the conversation (PHASE-61 S6); without it nothing is."""
    if not (settings.llm_url and settings.llm_model):
        return None
    return ChatModel(settings.llm_url, settings.llm_model, settings.llm_api_key, settings.llm_timeout_s,
                     settings.llm_json_mode, extra_body=settings.llm_extra_body,
                     no_temperature=settings.llm_no_temperature,
                     observer=None if log_to is None else calls.observer(log_to, "note",
                                                                         conversation_id=conversation_id)
                     ).complete_metered


def make(ask: Ask, view: dict[str, Any], told: dict[str, Any] | None, last_turn: int | None,
         model: Callable[..., tuple[Any, ...]] | None, today: str,
         canon: list[dict[str, Any]] | None = None, language: str | None = None,
         semantic_leaks: LeakCheck | None = None) -> dict[str, Any]:
    """The note: one block holding every part asked for that has something to say, and what each part was made of.
    `canon` is the manifest in force with its texts (`canon.manifest`), which only the diverged part reads. `language`
    (default: the one asked for, `Ask.language`) and `semantic_leaks` go to the chronicle and the custom part."""
    language = ask.language if language is None else language
    facts = view.get("facts") or []
    # PHASE-67: a view read with the provisional finale (`include_open_turn`) names its reply's revision
    finale = str(view["open_turn"]["revision"]) if view.get("open_turn") else None
    parts: list[str] = []
    info = []
    for kind in ask.sections:
        if kind == "diverged":
            d = divergence.diverged(canon or [], view.get("entities") or [],
                                    [f for f in facts if ask.secrets or not kept(f)], told,
                                    [s for s in view.get("secrets") or [] if s.get("open")], last_turn,
                                    model if ask.model else None, ask.secrets, changed_lines(facts, ask.secrets),
                                    frozenset(view.get("excluded") or ()))
            body = d["body"]
            info.append({"kind": kind, **{k: d[k] for k in ("made", "cached", "held", "reason", "turns", "lines",
                                                            "entries", "left_out", "dropped")}, "chars": len(body)})
        elif kind == "custom":
            c = custom(ask.custom_prompt, told, view.get("threads") or [], facts, view.get("secrets") or [], ask.chars,
                       model if ask.model else None, ask.secrets, last_turn,
                       setting=(canon or []) if ask.custom_setting else None, entities=view.get("entities") or [],
                       excluded=frozenset(view.get("excluded") or ()), language=language,
                       semantic_leaks=semantic_leaks, finale=finale)
            body = c["body"]
            info.append({"kind": kind, **{k: c[k] for k in ("made", "cached", "held", "reason", "turns", "stale")},
                         **{k: c[k] for k in ("entries", "left_out") if k in c}, "chars": len(body)})
        elif kind == "chronicle":
            c = chronicle(told, view.get("threads") or [], facts, view.get("secrets") or [], ask.chars,
                          model if ask.model else None, ask.secrets, last_turn, language, semantic_leaks, finale)
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
    out = {"text": text, "chars": len(text), "sections": info, "last_turn": last_turn}
    if view.get("open_turn"):  # PHASE-67: the note read the provisional finale (provenance; absent otherwise)
        out["open_turn"] = {k: view["open_turn"][k] for k in ("turn", "revision", "host_logical_id")}
    return out
