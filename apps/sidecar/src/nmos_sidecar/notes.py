"""Notes for the author's note (PHASE-50): sections the owner pastes into a chat's author's note, made on request.

Three kinds: the chronicle (the story's events, how they went and ended, from the scene summaries and the threads; one
model call, with an assembled fallback), what changed from the setting (canon values a story fact now supersedes) and
address and standing (each pair's relationship, role, feeling and form of address). Each is written between two marker
lines. The author's note is canon (ADR 0045), so the canon never reads a marked block: the plugin removes them before
the hash, and `canonfacts.process` again before a read (an older plugin sends them whole).

Nothing is stored and no packet reads these sections: they are views of memory, made when asked.
"""

from __future__ import annotations

from typing import Any

from .facts import symmetric
from .inspector import _named, pairs
from .noteblocks import KINDS, LABELS, strip_blocks, wrap  # noqa: F401  (the API's names for them)
from .predicates import HOLDER_PER_ITEM, REGISTRY

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
