"""Memory on a time axis for the browser Inspector (PHASE-32): a character's facts as bars over turns, and one line
per character on the conversation page.

Read-only rendering of the Inspector's memory view: every bar is a history entry `facts.py` already folded (turn and
outcome), a thread from its opening to its closing turn, or an event. Nothing here is read by recall or the packet.
The caller passes its translator `t` and draws this only outside the panel (`embed`), whose sanitizer drops `style`.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Callable, Iterable
from html import escape
from typing import Any

from .entities import norm

RECENT = 25  # the recent window, in turns (PHASE-32 Q7, owner)
LANES = 40  # lanes per section (Q8)
DOTS = 200  # event dots on a character page (Q8)
TICKS = 120  # ticks on one cast line (Q8)
RELATIONS = ("relationship", "role_toward", "feels_toward", "addresses")  # from this character (Q5)
SALIENCE = {"major": "s-major", "minor": "s-minor"}

T = Callable[[str], str]

# The browser page's only script (PHASE-32 Q3): a bar shows its detail, rendered next to it by the sidecar, in the side
# column. Without it a bar is a link to its fact's row.
SCRIPT = ("<script>document.addEventListener('click',function(e){var a=e.target.closest('.tl [data-d]');if(!a)return;"
          "e.preventDefault();var box=a.closest('.tl');box.querySelectorAll('.tl-card').forEach(function(c){"
          "c.hidden=c.id!==a.dataset.d});box.querySelectorAll('[aria-pressed]').forEach(function(b){"
          "b.setAttribute('aria-pressed','false')});a.setAttribute('aria-pressed','true')});</script>")


def _v(value: Any) -> str:
    return escape("" if value is None else str(value))


def window(now: int | None, span: str | None) -> tuple[int, int]:
    """The turns drawn: the whole chat, or its last RECENT turns (`span=recent`)."""
    hi = max(now or 0, 0)
    return (max(0, hi - RECENT + 1) if span == "recent" else 0), hi


def _start(entry: dict[str, Any]) -> int | None:
    """Where an entry starts: its turn, or 0 for a canon statement (before turn 0, ADR 0047)."""
    if entry.get("canon"):
        return 0
    return entry.get("turn") if isinstance(entry.get("turn"), int) else None


def segments(fact: dict[str, Any], now: int) -> list[dict[str, Any]]:
    """A fact's history as spans of turns: each entry until the next one starts; the current one until now; a closed last
    one on its own turn. Entries without a turn (legacy rows) are left out."""
    history = [h for h in (fact.get("history") or [fact]) if _start(h) is not None]
    out = []
    for i, h in enumerate(history):
        start = _start(h)
        outcome = h.get("outcome", "current" if h is fact else "superseded")
        if i + 1 < len(history):
            end = max(start, _start(history[i + 1]) - 1)
        else:
            end = max(start, now) if outcome == "current" else start
        out.append({"start": start, "end": end, "outcome": outcome, "canon": bool(h.get("canon")),
                    "negative": h.get("polarity") == "negative", "value": h.get("value") or h.get("object") or "",
                    "turn": h.get("turn")})
    if out and fact.get("owner") and out[-1]["outcome"] == "current":
        out[-1]["owner"] = True  # only the current version carries the owner's mark (PHASE-32 Q10)
    return out


class _Page:
    """Bars and their detail cards for one timeline, numbered in order; the first current bar starts selected."""

    def __init__(self, t: T, lo: int, hi: int):
        self.t, self.lo, self.hi, self.cards, self.picked = t, lo, hi, [], None

    def pct(self, turn: int) -> float:
        return round((turn - self.lo) / (self.hi - self.lo + 1) * 100, 3)

    def card(self, body: str, selected: bool) -> str:
        cid = f"tl-{len(self.cards)}"
        if self.picked is None and selected:
            self.picked = cid
        self.cards.append((cid, body))
        return cid

    def span_text(self, start: int, end: int, current: bool) -> str:
        return f"t{start} – {self.t('tl.now') if current else f't{end}'}"


def _outcome(t: T, outcome: str) -> str:
    return t(f"o.{outcome}")


def _bars(p: _Page, lane: str, fact: dict[str, Any], segs: list[dict[str, Any]]) -> str:
    out = []
    history = "".join(f"<li{' class=\"cur\"' if s['outcome'] == 'current' else ''}><span class=\"muted\">"
                      f"{p.span_text(s['start'], s['end'], s['outcome'] == 'current')}</span> {_value(p.t, s)}</li>"
                      for s in segs)
    for s in segs:
        if s["end"] < p.lo:
            continue
        a, cur = max(s["start"], p.lo), s["outcome"] == "current"
        left, width = p.pct(a), round(p.pct(s["end"] + 1) - p.pct(a), 3)
        when = p.span_text(s["start"], s["end"], cur)
        marks = (f"<p class=\"muted\">{_v(p.t('tl.canon'))}</p>" if s["canon"] else "") + \
                (f"<p class=\"warn\">{_v(p.t('tl.owner'))}</p>" if s.get("owner") else "")
        cid = p.card(f"<p class=\"muted\">{_v(lane)}</p><p class=\"v\">{_value(p.t, s)}</p>"
                     f"<p>{_v(when)} · {_v(_outcome(p.t, s['outcome']))}</p>{marks}"
                     + (f"<ol class=\"tl-hist\">{history}</ol>" if len(segs) > 1 else "")
                     + f"<p><a href=\"#a-{_v(fact['id'])}\">{_v(p.t('tl.row'))}</a></p>", cur)
        cls = "tl-bar" + ("" if cur else " past") + (" neg" if s["negative"] else "") + \
              (" canon" if s["canon"] else "") + (" owner" if s.get("owner") else "")
        title = f"{lane}: {_plain(p.t, s)} · {when} · {_outcome(p.t, s['outcome'])}"
        out.append(f"<a class=\"{cls}\" href=\"#a-{_v(fact['id'])}\" data-d=\"{cid}\" aria-pressed=\"{{{cid}}}\" "
                   f"style=\"left:{left}%;width:calc({width}% - 2px)\" title=\"{_v(title)}\">"
                   f"{_value(p.t, s) if width >= 8 else ''}</a>")
    return "".join(out)


def _plain(t: T, s: dict[str, Any]) -> str:
    return f"{s['value']} ({t('w.not')})" if s["negative"] else str(s["value"])


def _value(t: T, s: dict[str, Any]) -> str:
    return _v(_plain(t, s))


def _row(label: str, track: str, cls: str = "") -> str:
    return (f"<div class=\"tl-row{cls}\"><div class=\"tl-lab\" title=\"{_v(label)}\">{_v(label)}</div>"
            f"<div class=\"tl-track\"><i class=\"tl-rule\"></i>{track}</div></div>")


def _axis(p: _Page) -> str:
    step = 5 if p.hi - p.lo < 40 else 10 if p.hi - p.lo < 200 else 50
    marks = [p.lo] + [x for x in range((p.lo // step + 1) * step, p.hi - step // 2, step)] + [p.hi]
    spans = "".join(f"<span style=\"left:{p.pct(m) if m != p.hi else 100}%\""
                    f"{' class=\"first\"' if i == 0 else ' class=\"last\"' if i == len(marks) - 1 else ''}>"
                    f"{_v(p.t('tl.now_at').format(n=m) if m == p.hi else f't{m}')}</span>"
                    for i, m in enumerate(marks))
    return f"<div class=\"tl-row tl-axis\" aria-hidden=\"true\"><div></div><div class=\"tl-track\">{spans}</div></div>"


def _group(p: _Page, title: str, rows: list[str], more: int) -> str:
    if not rows:
        return ""
    rest = f"<p class=\"muted tl-more\">{_v(p.t('tl.more').format(n=more))}</p>" if more else ""
    return f"<div class=\"tl-group\"><h3>{_v(title)}</h3>{''.join(rows)}{rest}</div>"


def _label(t: T, predicate: str, obj: str | None = None) -> str:
    name = t(f"p.{predicate}")
    return f"{name} → {obj}" if obj else name


def character(t: T, entity_id: str, facts: list[dict[str, Any]], threads: list[dict[str, Any]],
              names: Iterable[str], now: int | None, span: str | None, switch: str) -> str:
    """One character's timeline (PHASE-32 scope 1): state, relationships from them, threads and events, with the
    detail column. `names` are the character's normalized names (threads name their holder as text), `switch` the
    time-window links."""
    lo, hi = window(now, span)
    p = _Page(t, lo, hi)

    def mine(f: dict[str, Any]) -> bool:
        return (f.get("subject_entity") or {}).get("id") == entity_id

    def latest(f: dict[str, Any]) -> int:
        return max((s["start"] for s in segments(f, hi)), default=-1)

    own = [f for f in facts if mine(f) and f.get("predicate") not in ("event", "knows")]
    state = sorted((f for f in own if f["predicate"] not in RELATIONS), key=latest, reverse=True)
    rels = sorted((f for f in own if f["predicate"] in RELATIONS and f.get("object")),
                  key=lambda f: (f["object"], RELATIONS.index(f["predicate"])))

    def lanes(rows: list[dict[str, Any]], label: Callable[[dict[str, Any]], str]) -> tuple[list[str], int]:
        drawn = []
        for f in rows:
            segs = [s for s in segments(f, hi) if s["end"] >= lo]
            if segs:
                drawn.append((f, segs))
        return [_row(label(f), _bars(p, label(f), f, segs)) for f, segs in drawn[:LANES]], max(0, len(drawn) - LANES)

    state_rows, state_more = lanes(state, lambda f: _label(t, f["predicate"]))
    rel_rows, rel_more = lanes(rels, lambda f: _label(t, f["predicate"], f["object"]))

    held = set(names)
    thread_rows = []
    for th in sorted((th for th in threads if norm(th.get("by")) in held or norm(th.get("to")) in held),
                     key=lambda th: th.get("turn") or 0):
        start = th.get("turn")
        if not isinstance(start, int):
            continue
        closed = th.get("closed_by") or {}
        end = closed.get("turn") if isinstance(closed.get("turn"), int) else None
        current = th.get("status") == "open"
        stop = hi if current else max(start, end if end is not None else start)
        if stop < lo:
            continue
        a = max(start, lo)
        left, width = p.pct(a), round(p.pct(stop + 1) - p.pct(a), 3)
        state_word = t(f"t.{th.get('status')}")
        lane = th.get("text") or t(f"k.{th.get('kind', 'promise')}")
        when = p.span_text(start, stop, current)
        cid = p.card(f"<p class=\"muted\">{_v(t('tl.threads'))}</p><p class=\"v\">{_v(lane)}</p>"
                     f"<p>{_v(when)} · {_v(state_word)}</p>"
                     f"<p class=\"muted\">{_v(th.get('by') or '')}{' → ' + _v(th['to']) if th.get('to') else ''}</p>"
                     f"<p><a href=\"#a-{_v(th['id'])}\">{_v(t('tl.row'))}</a></p>", False)
        thread_rows.append(_row(lane, f"<a class=\"tl-bar{'' if current else ' past'}{' open' if current else ''}\" "
                                      f"href=\"#a-{_v(th['id'])}\" data-d=\"{cid}\" aria-pressed=\"{{{cid}}}\" "
                                      f"style=\"left:{left}%;width:calc({width}% - 2px)\" "
                                      f"title=\"{_v(f'{lane} · {when} · {state_word}')}\">"
                                      f"{_v(state_word) if width >= 8 else ''}</a>"))

    def takes_part(f: dict[str, Any]) -> bool:
        return mine(f) or any((x.get("entity") or {}).get("id") == entity_id for x in f.get("participant_entities") or [])

    events = sorted((f for f in facts if f.get("predicate") == "event" and takes_part(f)
                     and isinstance(f.get("turn"), int) and lo <= f["turn"] <= hi), key=lambda f: f["turn"])
    dots = []
    for f in events[-DOTS:]:
        size = SALIENCE.get(f.get("salience") or "", "s-mid")
        cid = p.card(f"<p class=\"muted\">{_v(t('tl.events'))}</p><p class=\"v\">{_v(f.get('value') or '')}</p>"
                     f"<p>t{_v(f['turn'])}{' · ' + _v(t('s.' + f['salience'])) if f.get('salience') in SALIENCE else ''}"
                     f"</p><p><a href=\"#a-{_v(f['id'])}\">{_v(t('tl.row'))}</a></p>", False)
        title = f"t{f['turn']} · {f.get('value') or ''}"
        dots.append(f"<a class=\"tl-dot {size}\" href=\"#a-{_v(f['id'])}\" data-d=\"{cid}\" aria-pressed=\"{{{cid}}}\" "
                    f"style=\"left:{p.pct(f['turn'])}%\" title=\"{_v(title)}\"></a>")

    groups = (_group(p, t("tl.state"), state_rows, state_more)
              + _group(p, t("tl.relations"), rel_rows, rel_more)
              # the newest threads, as the threads table lists the newest 100
              + _group(p, t("tl.threads"), thread_rows[-LANES:], max(0, len(thread_rows) - LANES))
              + (_group(p, t("tl.events"), [_row(t("tl.n_events").format(n=len(dots)), "".join(dots))],
                        max(0, len(events) - DOTS)) if dots else ""))
    if not groups:
        return f"<div class=\"tl\">{switch}<p class=\"muted\">{_v(t('tl.empty'))}</p></div>"
    cards = "".join(f"<div class=\"tl-card\" id=\"{cid}\"{'' if cid == p.picked else ' hidden'}>{body}</div>"
                    for cid, body in p.cards)
    html = (f"<div class=\"tl\">{switch}<div class=\"tl-grid\"><div class=\"tl-main\">{_axis(p)}{groups}</div>"
            f"<aside class=\"tl-side\">{cards or ''}<p class=\"muted tl-hint\">{_v(t('tl.hint'))}</p></aside></div></div>")
    # the first current bar starts selected; a value never forms a placeholder (its quotes are escaped)
    html = re.sub(r'aria-pressed="\{(tl-\d+)\}"',
                  lambda m: f'aria-pressed="{"true" if m.group(1) == p.picked else "false"}"', html)
    return html + SCRIPT


def changes(entity_id: str, facts: list[dict[str, Any]], now: int) -> list[int]:
    """The turns a character's memory changed: every history entry of their facts starts one, a closed last entry ends
    one, and every event they take part in."""
    turns: set[int] = set()
    for f in facts:  # the caller may pass only the facts that concern this character (`by_character`)
        subject = (f.get("subject_entity") or {}).get("id") == entity_id
        part = any((x.get("entity") or {}).get("id") == entity_id for x in f.get("participant_entities") or [])
        if f.get("predicate") == "event":
            if (subject or part) and isinstance(f.get("turn"), int):
                turns.add(f["turn"])
            continue
        if not subject or f.get("predicate") == "knows":
            continue
        segs = segments(f, now)
        for s in segs:
            if not s["canon"]:
                turns.add(s["start"])
        if segs and segs[-1]["outcome"] != "current":
            turns.add(segs[-1]["end"] + 1)
    return sorted(x for x in turns if x <= now)


def by_character(facts: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """The facts each character's line reads: those they are the subject of, and the events they take part in."""
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for f in facts:
        ids = {(f.get("subject_entity") or {}).get("id")}
        if f.get("predicate") == "event":
            ids |= {(x.get("entity") or {}).get("id") for x in f.get("participant_entities") or []}
        for i in ids - {None}:
            out[i].append(f)
    return out


def cast(t: T, entities: list[dict[str, Any]], facts: list[dict[str, Any]], scene_ids: list[str], now: int | None,
         span: str | None, link: Callable[[str], str], switch: str) -> str:
    """One line per character (PHASE-32 scope 2): the current scene's cast first, every other character folded; a tick
    where their memory changed, the last change, a link to their page. The persona is not a cast line (ADR 0023)."""
    lo, hi = window(now, span)
    p = _Page(t, lo, hi)
    people = [e for e in entities if e.get("type") == "character" and not e.get("persona")]
    by_id = {e["id"]: e for e in people}
    first = [by_id[i] for i in dict.fromkeys(scene_ids) if i in by_id]
    rest = sorted((e for e in people if e not in first), key=lambda e: -(e.get("mentions") or 0))
    mine = by_character(facts)

    def line(e: dict[str, Any]) -> str:
        turns = changes(e["id"], mine.get(e["id"], []), hi)
        last = turns[-1] if turns else None
        shown = [x for x in turns if x >= lo][-TICKS:]
        ticks = "".join(f"<i class=\"tl-tick\" style=\"left:{p.pct(x)}%\"></i>" for x in shown)
        when = f"t{last}" if last is not None else "—"
        label = f"{e['name']} · {when}"
        return (f"<a class=\"tl-row tl-line\" href=\"{_v(link(e['id']))}\" title=\"{_v(label)}\">"
                f"<span class=\"tl-lab\">{_v(e['name'])}<span class=\"muted\"> {_v(when)}</span></span>"
                f"<span class=\"tl-track\"><i class=\"tl-rule\"></i>{ticks}</span></a>")

    if not people:
        return f"<div class=\"tl\">{switch}<p class=\"muted\">{_v(t('tl.no_cast'))}</p></div>"
    head = f"<p class=\"muted\">{_v(t('tl.cast_note'))}</p>"
    shown = "".join(line(e) for e in first) if first else ""
    folded = ""
    if rest:
        inner = "".join(line(e) for e in rest)
        folded = (f"<details class=\"tl-others\"{'' if first else ' open'}><summary>"
                  f"{_v(t('tl.others').format(n=len(rest)))}</summary>{inner}</details>")
    return f"<div class=\"tl tl-cast\">{switch}{head}{_axis(p)}{shown}{folded}</div>"


STYLE = """
.tl{margin:6px 0 18px} .tl h3{font-size:12px;font-weight:600;color:var(--muted);margin:14px 0 2px}
.tl-switch{font-size:13px;margin:0 0 8px}
.tl-grid{display:grid;grid-template-columns:minmax(0,1fr) 260px;gap:20px;align-items:start}
.tl-row{display:grid;grid-template-columns:120px minmax(0,1fr);gap:10px;align-items:center;min-height:24px;color:inherit}
a.tl-row:hover{background:var(--chip);text-decoration:none}
.tl-lab{font-size:12px;color:var(--fg);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.tl-track{position:relative;height:22px;min-width:0}
.tl-rule{position:absolute;left:0;right:0;top:11px;height:1px;background:var(--line)}
.tl-bar{position:absolute;top:2px;height:18px;border-radius:3px;font-size:11px;line-height:16px;padding:0 5px;
  overflow:hidden;white-space:nowrap;box-sizing:border-box;background:var(--chip);color:var(--fg);border:1px solid var(--line)}
.tl-bar:hover{text-decoration:none;border-color:var(--muted)}
.tl-bar.past{background:var(--bg);color:var(--muted)} .tl-bar.neg{font-style:italic}
.tl-bar.open{border-right-style:dashed} .tl-bar.canon{border-left:2px dotted var(--muted)}
.tl-bar.owner{border-color:#e8590c}
.tl [aria-pressed="true"]{background:var(--accent);color:var(--bg);border-color:var(--accent)}
.tl-dot{position:absolute;top:50%;width:10px;height:10px;margin:-5px 0 0 -5px;border-radius:50%;background:var(--muted)}
.tl-dot.s-major{width:14px;height:14px;margin:-7px 0 0 -7px;background:var(--fg)}
.tl-dot.s-minor{width:8px;height:8px;margin:-4px 0 0 -4px;background:var(--bg);border:1.5px solid var(--muted);box-sizing:border-box}
.tl-tick{position:absolute;top:4px;width:2px;height:14px;margin-left:-1px;background:var(--muted)}
.tl-axis .tl-track span{position:absolute;top:2px;font-size:11px;color:var(--muted);transform:translateX(-50%);white-space:nowrap}
.tl-axis .tl-track span.first{transform:none} .tl-axis .tl-track span.last{transform:translateX(-100%)}
.tl-side{border-left:1px solid var(--line);padding-left:14px;font-size:13px;position:sticky;top:12px}
.tl-side p{margin:2px 0} .tl-side .v{font-size:17px;font-weight:600;margin:4px 0}
.tl-hist{margin:6px 0;padding-left:18px;color:var(--muted)} .tl-hist .cur{color:var(--fg)}
.tl-more,.tl-hint{font-size:12px} .tl-others summary{font-size:13px;color:var(--muted);margin:6px 0}
tr:target td{background:var(--chip)}
@media (max-width:720px){.tl-grid{grid-template-columns:minmax(0,1fr)}
  .tl-side{position:static;border-left:0;border-top:1px solid var(--line);padding:10px 0 0}
  .tl-row{grid-template-columns:minmax(0,1fr);gap:0}}
"""
