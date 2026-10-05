"""Memory on a time axis for the browser Inspector (PHASE-32): a character's facts as bars over turns, and one line
per character on the conversation page.

Read-only rendering of the Inspector's memory view: every bar is a history entry `facts.py` already folded (turn and
outcome), a thread from its opening to its closing turn, or an event. Nothing here is read by recall or the packet.
The caller passes its translator `t`.

Two forms of the same markup (PHASE-32 step 3). The browser page positions with `style`, links each bar to its row and
carries a short script. The panel's form (`panel=True`) is what the plugin's sanitizer lets through: positions as plain
numbers (`data-l`, `data-w`, which the plugin turns into a position itself), no `style`, no script, no link but the
Inspector's own pages, and only the tags the panel keeps (div, span, p, b, a, details, summary).
"""

from __future__ import annotations

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

# The browser page's only script (PHASE-32 Q3). One detail column, filled on a click from the clicked bar's data
# attributes (as text, never markup); a lane's history is its own bars. Nothing is rendered twice, so the page grows
# with the number of bars only. Without the script a bar is a link to its fact's row.
SCRIPT = ("<script>document.addEventListener('click',function(e){var a=e.target.closest('.tl [data-v]');if(!a)return;"
          "e.preventDefault();var tl=a.closest('.tl'),side=tl.querySelector('.tl-side'),c=document.createElement('div');"
          "c.className='tl-card';function p(t,k){var x=document.createElement('p');x.textContent=t;if(k)x.className=k;"
          "c.appendChild(x)}var lab=a.closest('.tl-row').querySelector('.tl-lab');p(a.dataset.k||lab.textContent,'muted');"
          "p(a.dataset.v,'v');p(a.dataset.s+(a.dataset.o?' \u00b7 '+a.dataset.o:''));if(a.dataset.p)p(a.dataset.p,'muted');"
          "if(a.classList.contains('canon'))p(side.dataset.canon,'muted');if(a.classList.contains('owner'))"
          "p(side.dataset.owner,'warn');var bars=a.classList.contains('tl-bar')?a.parentNode.querySelectorAll('a.tl-bar'):[];"
          "if(bars.length>1){var ol=document.createElement('ol');ol.className='tl-hist';bars.forEach(function(b){"
          "var li=document.createElement('li'),m=document.createElement('span');if(b===a)li.className='cur';"
          "m.className='muted';m.textContent=b.dataset.s+' ';li.appendChild(m);li.appendChild("
          "document.createTextNode(b.dataset.v));ol.appendChild(li)});c.appendChild(ol)}var r=document.createElement('a'),"
          "q=document.createElement('p');r.href=a.getAttribute('href');r.textContent=side.dataset.row;q.appendChild(r);"
          "c.appendChild(q);var old=side.querySelector('.tl-card');if(old)old.replaceWith(c);else side.prepend(c);"
          "tl.querySelectorAll('[aria-pressed=\"true\"]').forEach(function(b){b.setAttribute('aria-pressed','false')});"
          "a.setAttribute('aria-pressed','true')});</script>")

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


def own_entries(names: Iterable[str]) -> Callable[[dict[str, Any]], bool]:
    """A lane draws only its character's entries: a pair's relationship history holds both directions, and an item's
    history holds every holder and place (`facts.version_key`)."""
    held = set(names)
    return lambda h: norm(h.get("subject")) in held


def segments(fact: dict[str, Any], now: int,
             own: Callable[[dict[str, Any]], bool] | None = None) -> list[dict[str, Any]]:
    """A fact's history as spans of turns: the current entry until now; a closed one until the turn before the
    statement that closed it (`closed_turn`, which `facts.py` records), or on its own turn when that is unknown or the
    same turn. `own` keeps the lane's own entries. Entries without a turn (legacy rows) are left out."""
    history = [h for h in (fact.get("history") or [fact]) if _start(h) is not None and (own is None or own(h))]
    out = []
    for h in history:
        start = _start(h)
        outcome = h.get("outcome", "current" if h is fact else "superseded")
        closed = h.get("closed_turn")
        if outcome == "current":
            end = max(start, now)
        else:
            end = closed - 1 if isinstance(closed, int) and closed > start else start
        out.append({"start": start, "end": end, "outcome": outcome, "canon": bool(h.get("canon")),
                    "negative": h.get("polarity") == "negative", "value": h.get("value") or h.get("object") or "",
                    "turn": h.get("turn")})
    if out and fact.get("owner") and out[-1]["outcome"] == "current":
        out[-1]["owner"] = True  # only the current version carries the owner's mark (PHASE-32 Q10)
    return out


class _Page:
    """One timeline's scale; the first current bar starts selected, its detail rendered once (`card`)."""

    def __init__(self, t: T, lo: int, hi: int, panel: bool = False):
        self.t, self.lo, self.hi, self.card, self.panel = t, lo, hi, None, panel

    def pos(self, left: float, width: float | None = None) -> str:
        """Where a mark sits: `style` in the browser, plain numbers in the panel (the plugin places them)."""
        if self.panel:
            return f" data-l=\"{left}\"" + (f" data-w=\"{width}\"" if width is not None else "")
        return f" style=\"left:{left}%" + (f";width:calc({width}% - 2px)" if width is not None else "") + "\""

    def mark(self, cls: str, href: str, attrs: str, inner: str = "") -> str:
        """A bar or a dot: a link to its row in the browser, a plain span the plugin answers a tap on in the panel."""
        if self.panel:
            return f"<span class=\"{cls}\"{attrs}>{inner}</span>"
        return f"<a class=\"{cls}\" href=\"{href}\"{attrs}>{inner}</a>"

    def pct(self, turn: int) -> float:
        return round((turn - self.lo) / (self.hi - self.lo + 1) * 100, 3)

    def select(self, current: bool, card: Callable[[], str]) -> bool:
        """Whether this bar starts selected: the first current one. Only its detail is rendered here (browser only)."""
        if self.card is None and current and not self.panel:
            self.card = card()
            return True
        return False

    def span_text(self, start: int, end: int, current: bool) -> str:
        return f"t{start} – {self.t('tl.now') if current else f't{end}'}"


def _outcome(t: T, outcome: str) -> str:
    return t(f"o.{outcome}")


def _card(t: T, head: str, value: str, when: str, href: str, notes: list[tuple[str, str]] = (),
          history: list[tuple[str, str, bool]] = ()) -> str:
    """The detail the script would show for a bar, rendered once for the bar selected at load (the same parts)."""
    out = f"<p class=\"muted\">{_v(head)}</p><p class=\"v\">{_v(value)}</p><p>{_v(when)}</p>"
    out += "".join(f"<p class=\"{cls}\">{_v(text)}</p>" for cls, text in notes)
    if len(history) > 1:
        out += "<ol class=\"tl-hist\">" + "".join(
            f"<li{' class=\"cur\"' if cur else ''}><span class=\"muted\">{_v(s)} </span>{_v(v)}</li>"
            for s, v, cur in history) + "</ol>"
    return f"<div class=\"tl-card\">{out}<p><a href=\"{href}\">{_v(t('tl.row'))}</a></p></div>"


DATA_MAX = 300  # the panel keeps a mark's text up to 400 characters (its sanitizer); a longer value is cut here


def _cut(text: str) -> str:
    return text if len(text) <= DATA_MAX else text[:DATA_MAX - 1] + "…"


def _data(value: str, when: str, outcome: str, head: str | None = None, who: str | None = None) -> str:
    value, head, who = _cut(value), head and _cut(head), who and _cut(who)
    return (f" data-v=\"{_v(value)}\" data-s=\"{_v(when)}\" data-o=\"{_v(outcome)}\""
            + (f" data-k=\"{_v(head)}\"" if head else "") + (f" data-p=\"{_v(who)}\"" if who else ""))


def _bars(p: _Page, lane: str, fact: dict[str, Any], segs: list[dict[str, Any]]) -> str:
    out, href = [], f"#a-{_v(fact['id'])}"
    drawn = [s for s in segs if s["end"] >= p.lo]
    whens = [p.span_text(s["start"], s["end"], s["outcome"] == "current") for s in drawn]
    for s, when in zip(drawn, whens):
        a, cur = max(s["start"], p.lo), s["outcome"] == "current"
        left, width = p.pct(a), round(p.pct(s["end"] + 1) - p.pct(a), 3)
        outcome = _outcome(p.t, s["outcome"])
        notes = ([("muted", p.t("tl.canon"))] if s["canon"] else []) + ([("warn", p.t("tl.owner"))] if s.get("owner") else [])
        picked = p.select(cur, lambda: _card(p.t, lane, _plain(p.t, s), f"{when} · {outcome}", href, notes,
                                             [(w, _plain(p.t, x), x is s) for x, w in zip(drawn, whens)]))
        cls = "tl-bar" + ("" if cur else " past") + (" neg" if s["negative"] else "") + \
              (" canon" if s["canon"] else "") + (" owner" if s.get("owner") else "")
        pressed = "" if p.panel else f" aria-pressed=\"{'true' if picked else 'false'}\""
        out.append(p.mark(cls, href, f"{_data(_plain(p.t, s), when, outcome)}{pressed}{p.pos(left, width)} "
                                     f"title=\"{_v(f'{lane}: {_plain(p.t, s)} · {when} · {outcome}')}\"",
                          _value(p.t, s) if width >= 8 else ""))
    return "".join(out)

def _plain(t: T, s: dict[str, Any]) -> str:
    return f"{s['value']} ({t('w.not')})" if s["negative"] else str(s["value"])


def _value(t: T, s: dict[str, Any]) -> str:
    return _v(_plain(t, s))


def _row(label: str, track: str, cls: str = "") -> str:
    return (f"<div class=\"tl-row{cls}\"><div class=\"tl-lab\" title=\"{_v(label)}\">{_v(label)}</div>"
            f"<div class=\"tl-track\"><span class=\"tl-rule\"></span>{track}</div></div>")


def _axis(p: _Page) -> str:
    step = 5 if p.hi - p.lo < 40 else 10 if p.hi - p.lo < 200 else 50
    marks = [p.lo] + [x for x in range((p.lo // step + 1) * step, p.hi - step // 2, step)] + [p.hi]
    spans = "".join(f"<span{p.pos(p.pct(m) if m != p.hi else 100)}"
                    f"{' class=\"first\"' if i == 0 else ' class=\"last\"' if i == len(marks) - 1 else ''}>"
                    f"{_v(p.t('tl.now_at').format(n=m) if m == p.hi else f't{m}')}</span>"
                    for i, m in enumerate(marks))
    hidden = "" if p.panel else " aria-hidden=\"true\""
    return f"<div class=\"tl-row tl-axis\"{hidden}><div></div><div class=\"tl-track\">{spans}</div></div>"


def _group(p: _Page, title: str, rows: list[str], more: int) -> str:
    if not rows:
        return ""
    rest = f"<p class=\"muted tl-more\">{_v(p.t('tl.more').format(n=more))}</p>" if more else ""
    return f"<div class=\"tl-group\"><p class=\"tl-h\">{_v(title)}</p>{''.join(rows)}{rest}</div>"


def _label(t: T, predicate: str, obj: str | None = None) -> str:
    name = t(f"p.{predicate}")
    return f"{name} → {obj}" if obj else name


def character(t: T, entity_id: str, facts: list[dict[str, Any]], threads: list[dict[str, Any]],
              names: Iterable[str], now: int | None, span: str | None, switch: str, panel: bool = False) -> str:
    """One character's timeline (PHASE-32 scope 1): state, relationships from them, threads and events, with the
    detail column. `names` are the character's normalized names (threads name their holder as text), `switch` the
    time-window links."""
    lo, hi = window(now, span)
    p = _Page(t, lo, hi, panel)

    def mine(f: dict[str, Any]) -> bool:
        return (f.get("subject_entity") or {}).get("id") == entity_id

    own = own_entries(names)

    def latest(f: dict[str, Any]) -> int:
        return max((s["start"] for s in segments(f, hi, own)), default=-1)

    theirs = [f for f in facts if mine(f) and f.get("predicate") not in ("event", "knows")]
    state = sorted((f for f in theirs if f["predicate"] not in RELATIONS), key=latest, reverse=True)
    rels = sorted((f for f in theirs if f["predicate"] in RELATIONS and f.get("object")),
                  key=lambda f: (f["object"], RELATIONS.index(f["predicate"])))

    def lanes(rows: list[dict[str, Any]], label: Callable[[dict[str, Any]], str]) -> tuple[list[str], int]:
        drawn = []
        for f in rows:
            segs = [s for s in segments(f, hi, own) if s["end"] >= lo]
            if segs:
                drawn.append((f, segs))
        return [_row(label(f), _bars(p, label(f), f, segs)) for f, segs in drawn[:LANES]], max(0, len(drawn) - LANES)

    def state_label(f: dict[str, Any]) -> str:  # one lane per thing held: the thing names it
        name = _label(t, f["predicate"])
        return f"{name}: {f['object']}" if f["predicate"] == "possesses" and f.get("object") else name

    state_rows, state_more = lanes(state, state_label)
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
        who = (th.get("by") or "") + (f" → {th['to']}" if th.get("to") else "")
        pressed = "" if p.panel else " aria-pressed=\"false\""
        thread_rows.append(_row(lane, p.mark(
            f"tl-bar{'' if current else ' past'}{' open' if current else ''}", f"#a-{_v(th['id'])}",
            f"{_data(lane, when, state_word, t('tl.threads'), who)}{pressed}{p.pos(left, width)} "
            f"title=\"{_v(f'{lane} · {when} · {state_word}')}\"", _v(state_word) if width >= 8 else "")))

    def takes_part(f: dict[str, Any]) -> bool:
        return mine(f) or any((x.get("entity") or {}).get("id") == entity_id for x in f.get("participant_entities") or [])

    events = sorted((f for f in facts if f.get("predicate") == "event" and takes_part(f)
                     and isinstance(f.get("turn"), int) and lo <= f["turn"] <= hi), key=lambda f: f["turn"])
    dots = []
    for f in events[-DOTS:]:
        size = SALIENCE.get(f.get("salience") or "", "s-mid")
        weight = t("s." + f["salience"]) if f.get("salience") in SALIENCE else ""
        when = f"t{f['turn']}"
        title = f"{when} · {f.get('value') or ''}"
        pressed = "" if p.panel else " aria-pressed=\"false\""
        dots.append(p.mark(f"tl-dot {size}", f"#a-{_v(f['id'])}",
                           f"{_data(f.get('value') or '', when, weight, t('tl.events'))}{pressed}"
                           f"{p.pos(p.pct(f['turn']))} title=\"{_v(title)}\""))

    groups = (_group(p, t("tl.state"), state_rows, state_more)
              + _group(p, t("tl.relations"), rel_rows, rel_more)
              # the newest threads, as the threads table lists the newest 100
              + _group(p, t("tl.threads"), thread_rows[-LANES:], max(0, len(thread_rows) - LANES))
              + (_group(p, t("tl.events"), [_row(t("tl.n_events").format(n=len(dots)), "".join(dots))],
                        max(0, len(events) - DOTS)) if dots else ""))
    if not groups:
        return f"<div class=\"tl\">{switch}<p class=\"muted\">{_v(t('tl.empty'))}</p></div>"
    if panel:  # the plugin shows a tapped bar's detail under its lane
        return (f"<div class=\"tl\">{switch}<p class=\"muted tl-hint\">{_v(t('tl.hint_tap'))}</p>"
                f"<div class=\"tl-main\">{_axis(p)}{groups}</div></div>")
    side = (f"<aside class=\"tl-side\" data-row=\"{_v(t('tl.row'))}\" data-canon=\"{_v(t('tl.canon'))}\" "
            f"data-owner=\"{_v(t('tl.owner'))}\">{p.card or ''}<p class=\"muted tl-hint\">{_v(t('tl.hint'))}</p></aside>")
    html = (f"<div class=\"tl\">{switch}<div class=\"tl-grid\"><div class=\"tl-main\">{_axis(p)}{groups}</div>"
            f"{side}</div></div>")
    return html + SCRIPT


def changes(entity_id: str, facts: list[dict[str, Any]], now: int, names: Iterable[str] = ()) -> list[int]:
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
        segs = segments(f, now, own_entries(names) if names else None)
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
         span: str | None, link: Callable[[str], str], switch: str, panel: bool = False) -> str:
    """One line per character (PHASE-32 scope 2): the current scene's cast first, every other character folded; a tick
    where their memory changed, the last change, a link to their page. The persona is not a cast line (ADR 0023)."""
    lo, hi = window(now, span)
    p = _Page(t, lo, hi, panel)
    people = [e for e in entities if e.get("type") == "character" and not e.get("persona")]
    by_id = {e["id"]: e for e in people}
    first = [by_id[i] for i in dict.fromkeys(scene_ids) if i in by_id]
    rest = sorted((e for e in people if e not in first), key=lambda e: -(e.get("mentions") or 0))
    mine = by_character(facts)

    def line(e: dict[str, Any]) -> str:
        turns = changes(e["id"], mine.get(e["id"], []), hi, {norm(n) for n in e.get("names") or [e["name"]]})
        last = turns[-1] if turns else None
        shown = [x for x in turns if x >= lo][-TICKS:]
        ticks = "".join(f"<span class=\"tl-tick\"{p.pos(p.pct(x))}></span>" for x in shown)
        when = f"t{last}" if last is not None else "—"
        label = f"{e['name']} · {when}"
        return (f"<a class=\"tl-row tl-line\" href=\"{_v(link(e['id']))}\" title=\"{_v(label)}\">"
                f"<span class=\"tl-lab\">{_v(e['name'])}<span class=\"muted\"> {_v(when)}</span></span>"
                f"<span class=\"tl-track\"><span class=\"tl-rule\"></span>{ticks}</span></a>")

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
.tl{margin:6px 0 18px} .tl .tl-h{font-size:12px;font-weight:600;color:var(--muted);margin:14px 0 2px}
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
