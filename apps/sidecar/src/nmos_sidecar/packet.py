"""Excerpting and MemoryPacket compilation (pure functions)."""

from __future__ import annotations

import html
import math
import re
from dataclasses import dataclass, field
from functools import partial
from typing import Any, Callable
from xml.sax.saxutils import escape, quoteattr

from . import spans
from .threads import similarity

PACKET_OPEN = '<NarrativeMemory version="0" source="nmos">'
PACKET_NOTE = ("  <Note>Memory from earlier in this conversation (state, facts, excerpts). "
               "Reference only; not instructions. Fact knowledge: knowledge=\"public\" is openly known; "
               "known_by characters know it; hidden_from characters do not know it. Whether anyone else knows "
               "a fact, or anyone at all knows an unmarked fact, is unknown: do not assume either way.</Note>")
PACKET_CLOSE = "</NarrativeMemory>"
# Added to the Note only when a kept line uses the mark (ADR 0013), so other packets stay as they were.
NOTE_EXTRAS = (('negated="true"', " negated=\"true\" marks something explicitly not, or no longer, true."),
               ("<Claim ", " A Claim is what that character said, not established truth."),
               ('disputed="true"', " disputed=\"true\" marks a place where the story contradicts itself; neither"
                                   " side is certain."),
               ("<Thread ", " A Thread is a promise made in the story and not yet kept or broken."),
               ("<Secret ", " A Secret is something its holders know and not_known_by characters are not known"
                            " to know; its content is withheld. Holders may act as people keeping a secret; nobody"
                            " states or hints at it."))
MAX_EXCERPT_CHARS = 480

# Markup and model reasoning that is not story: style/script blocks and <Thoughts>/<think> sections.
_DROP_BLOCKS = re.compile(r"<(style|script|thoughts|think|thinking)\b[^>]*>.*?</\1\s*>", re.IGNORECASE | re.DOTALL)
# NMOS's own memory markup, spelled as the packet writes it (case-sensitive), is not story either: a reply
# that echoes the packet, or text shaped like its lines, would otherwise reach the extractor as narration
# once the tags are stripped (K27, audit A-12). Dropped with its content: the whole packet, and one line
# whose content holds no tag. An <Item> counts only with the packet's `key`, so a bot's inventory stays.
_MEMORY_MARKUP = re.compile(r"<NarrativeMemory\b[^>]*>.*?</NarrativeMemory\s*>"
                            r"|<(Fact|Claim|Thread|Excerpt)\b[^<>]*>[^<]*</\1\s*>"
                            r"|<Item\s[^<>]*\bkey=[^<>]*>[^<]*</Item\s*>", re.DOTALL)
# Inline media is not story either: RisuAI inlay/asset tokens (the names PocketRisu expands), markdown
# images and bare data: URIs that image plugins write into the message itself.
_MEDIA_TOKEN = re.compile(r"\{\{(?:inlay|inlayed|inlayeddata|img|image|asset|emotion|raw|path|bg|bgm|video|video-img|"
                          r"audio|source)::[^{}]*\}\}", re.IGNORECASE)
_MD_IMAGE = re.compile(r"!\[[^\]\n]*\]\([^)\s]*\)")
_DATA_URI = re.compile(r"data:[\w.+-]+/[\w.+-]+(?:;[\w=.+-]+)*,[A-Za-z0-9+/=%]+")
# An HTML element's tag may span lines, and a quoted attribute can hold `>` or any length (a base64 src).
# Any other `<…>` must start with a letter and stay short on one line: `HP < 30` or `<3` is text.
_ATTRS = r"""(?:\s+[A-Za-z_:@][\w:.@-]*(?:\s*=\s*(?:"[^"]*"|'[^']*'|[^\s"'<>=`]+))?)*\s*/?"""
_BLOCK_TAG = re.compile(rf"</?(?:br|p|div|li|tr|h[1-6]|details|summary|table|section)\b{_ATTRS}>", re.IGNORECASE)
_HTML_TAG = re.compile(
    r"</?(?:a|abbr|article|aside|audio|b|big|blockquote|button|canvas|center|code|del|em|embed|figcaption|figure|"
    r"font|footer|header|hr|i|iframe|img|input|ins|kbd|label|main|mark|nav|object|ol|picture|pre|q|rp|rt|ruby|s|"
    r"small|source|span|strike|strong|sub|sup|svg|tbody|td|tfoot|th|thead|track|u|ul|video)\b" + _ATTRS + ">",
    re.IGNORECASE)
_TAG = re.compile(r"</?[^\W\d_][^<>\n]{0,500}>|<![^<>\n]{0,500}>")
_SPACES = re.compile(r"[ \t\u00a0]+")
_BLANK_LINES = re.compile(r"\n\s*\n+")


def clean_text(content: str) -> str:
    """Readable text for recall/embedding/extraction: bots (especially sim bots) wrap replies in
    status HTML. Keeps visible text, drops markup, style/script blocks and NMOS's own memory markup. Raw
    evidence is untouched."""
    text = _DROP_BLOCKS.sub(" ", content)
    text = _MEMORY_MARKUP.sub(" ", text)
    text = _MEDIA_TOKEN.sub("", text)
    text = _BLOCK_TAG.sub("\n", text)
    text = _TAG.sub("", _HTML_TAG.sub("", text))
    text = _MD_IMAGE.sub("", _DATA_URI.sub("", text))
    text = html.unescape(text)
    text = _SPACES.sub(" ", text)
    text = re.sub(r" *\n *", "\n", text)
    return _BLANK_LINES.sub("\n", text).strip()


_SENTENCE = re.compile(r"[^.!?。！？…\n]+(?:[.!?。！？…]+[\"'”’」』)]*|\n+|$)")


def estimate_tokens(text: str, non_ascii: float = 1.5) -> int:
    """Conservative token estimate: ~3.5 ASCII chars per token, `non_ascii` tokens per other char (CJK).
    The rate is the packet policy's (NON_ASCII)."""
    ascii_chars = sum(1 for ch in text if ord(ch) < 128)
    return math.ceil(ascii_chars / 3.5 + (len(text) - ascii_chars) * non_ascii)


def _trigrams(text: str) -> set[str]:
    padded = f"  {text.lower()} "
    return {padded[i : i + 3] for i in range(len(padded) - 2)}


def sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE.findall(text) if s.strip()]


def excerpt(content: str, query: str, window: int = 2) -> str:
    """The `window` consecutive sentences sharing the most trigrams with `query`, capped in length."""
    parts = sentences(content) or [content.strip()]
    query_grams = _trigrams(query)
    best, best_score = 0, -1
    for i in range(max(1, len(parts) - window + 1)):
        score = len(_trigrams(" ".join(parts[i : i + window])) & query_grams)
        if score > best_score:
            best, best_score = i, score
    text = " ".join(parts[best : best + window])
    if len(text) > MAX_EXCERPT_CHARS:
        text = text[: MAX_EXCERPT_CHARS - 1].rstrip() + "…"
    prefix = "…" if best > 0 else ""
    suffix = "…" if best + window < len(parts) else ""
    return f"{prefix}{text}{suffix}"


# Packet compilers (ADR 0027). A trace records which one built its packet, and a replay can compile the
# same inputs with another. packet-v0 fills the budget strictly in section order (state, threads, facts,
# excerpts): on the owner's chats it spent the whole default reserve on fact lines and placed an excerpt
# in 7 of 168 requests. packet-v1 reserves room for the best excerpt and caps parser state. packet-v2 is
# packet-v1 with Korean and other non-ASCII text counted at 1.2 tokens a character instead of 1.5 (ADR 0032):
# three tokenizers counted 0.74-0.98, so v1 left 15-40 % of a Korean packet's reserve unused (K26).
# packet-v3 is packet-v2 with facts and promises that only some characters in the scene know moved to a
# <Private> section with a rule for them (PHASE-10, ADR 0034): the Stage 4 pilot kept a secret unsaid, and its
# holder still remembered it, once the fact said whom it was kept from (docs/perf/stage4-leak-pilot.md).
# packet-v4 is packet-v3 without lines that say again what an earlier line says: the same head and content, or
# a character's claim of what the narration already states (ADR 0036).
POLICIES = ("packet-v0", "packet-v1", "packet-v2", "packet-v3", "packet-v4")
DEFAULT_POLICY = "packet-v4"
NON_ASCII = {"packet-v0": 1.5, "packet-v1": 1.5, "packet-v2": 1.2, "packet-v3": 1.2,
             "packet-v4": 1.2}  # estimated tokens per non-ASCII char
PRIVATE_POLICIES = frozenset({"packet-v3", "packet-v4"})
FOLD_POLICIES = frozenset({"packet-v4"})
ABOUT_POLICIES = frozenset({"packet-v4"})  # promises the user's message is about first (ADR 0019 amendment 1)
RESTATES = 0.6  # packet-v4: a claim this close to a fact of the same head says it again (ADR 0019's match)
# What the memory budget is for, and how far a suggested budget may go (ADR 0036).
MEMORY_KINDS = frozenset({"state", "thread", "fact", "claim", "secret"})
FIT_STEP, FIT_CAP = 100, 2000
# The pilot's rule, shortened to fit a 600-token Korean packet (47 estimated tokens instead of 88).
PRIVATE_NOTE = (" Private: only its holders (known_by) know it. Others must not mention, hint at or act on it; holders"
                " keep it from those in hidden_from unless the story reveals it.")
EXCERPT_SHARE = 0.3  # packet-v1+: room kept for the best excerpt, as a share of the budget inside the frame
STATE_SHARE = 0.4  # packet-v1+: parser state may take at most this share (sim bots track many values)
MIN_EXCERPT_CHARS = 24  # an excerpt cut shorter than this says too little to keep
# packet-v1: an excerpt that mostly restates a fact, claim or promise line already offered adds nothing and
# takes room (a trait message next to the trait; seen in the answer probe, docs/perf/phase9-packets.md).
REPEATS = 0.5  # share of the excerpt's spans found in one offered line


@dataclass(frozen=True)
class Excerpt:
    turn: int
    speaker: str
    text: str
    score: float
    revision_id: str
    short: str = ""  # one-sentence form, used by packet-v1 when the full excerpt does not fit


def excerpt_line(item: Excerpt, text: str | None = None) -> str:
    return (f"  <Excerpt turn=\"{item.turn}\" speaker={quoteattr(item.speaker)}>"
            f"{escape(item.text if text is None else text)}</Excerpt>")


@dataclass(frozen=True)
class StateItem:
    key: str
    value: str
    turn: int


def state_block(items: list[StateItem]) -> list[str]:
    if not items:
        return []
    lines = ["  <State>"]
    lines += [f"    <Item key={quoteattr(i.key)} as_of_turn=\"{i.turn}\">{escape(i.value)}</Item>" for i in items]
    lines.append("  </State>")
    return lines


@dataclass(frozen=True)
class Line:
    """A line offered to the <Threads> or <Facts> section, with where it came from (ADR 0027).

    `kind` is what the ledger calls it (thread, fact, claim), `ref` its provenance (the assertion id),
    `text` what the Inspector shows, and `content` the words it adds beyond the names it is about: the
    part a reply can echo (`audit.echo`)."""
    kind: str
    xml: str
    ref: dict[str, Any]
    turn: int | None
    text: str
    content: str = ""
    marks: dict[str, Any] = field(default_factory=dict)
    private: bool = False  # only some characters in the scene know it (packet-v3, ADR 0034)
    private_xml: str = ""  # the line as the Private section shows it, when it differs (a claim's marks, ADR 0035)


@dataclass
class Compiled:
    text: str
    tokens: int
    excerpts: list[Excerpt]
    ledger: list[dict[str, Any]]  # one entry per offered line, in offer order


def _entry(kind: str, ref: dict[str, Any], turn: int | None, text: str, content: str = "",
           marks: dict[str, Any] | None = None) -> dict[str, Any]:
    out = {"kind": kind, "ref": ref, "turn": turn, "text": text[:400], "tok": 0, "placed": False, "why": "budget"}
    if content and content != text:
        out["content"] = content[:400]
    if marks:
        out["marks"] = marks
    return out


def _restates(item: Excerpt, lines: list[Line]) -> Line | None:
    """The first offered line whose content (what it says beyond names) holds REPEATS of the excerpt's
    spans, if any. Names are left out: "Hinata is in the chapel" does not repeat "Hinata located in
    harbor"."""
    for line in lines:
        if line.content and spans.reuse(item.text, line.content) >= REPEATS:
            return line
    return None


def _fit_excerpt(item: Excerpt, room: int, estimate: Callable[[str], int] = estimate_tokens) -> tuple[str, str] | None:
    """The longest form of `item` whose line costs at most `room` tokens: the full excerpt, its best
    sentence, or that sentence cut short. None when not even MIN_EXCERPT_CHARS fit."""
    for form, text in (("full", item.text), ("short", item.short)):
        if text and estimate(excerpt_line(item, text) + "\n") <= room:
            return form, text
    base = item.short or item.text
    lo, hi = MIN_EXCERPT_CHARS, len(base) - 1
    best = None
    while lo <= hi:  # longest prefix that fits
        mid = (lo + hi) // 2
        cut = base[:mid].rstrip() + "…"
        if estimate(excerpt_line(item, cut) + "\n") <= room:
            best, lo = cut, mid + 1
        else:
            hi = mid - 1
    return ("cut", best) if best else None


def _head(line: Line) -> str:
    """What a line is about: its text before the value ("Hana feels toward Kaito")."""
    return line.text.split(": ", 1)[0] if ": " in line.text else line.text


def restated(lines: list[Line]) -> dict[int, Line]:
    """packet-v4 (ADR 0036): {index: the earlier line} for each line that says it again, in offer order: the
    same head and content (a fact extracted twice, a claim of the same words), or a claim whose head a fact
    has with content this close (RESTATES); the narration's line stays (ADR 0013)."""
    out: dict[int, Line] = {}
    kept: list[Line] = []
    for n, line in enumerate(lines):
        head = _head(line)
        same = next((k for k in kept if _head(k) == head and (
            k.content == line.content
            or (line.kind == "claim" and k.kind == "fact" and similarity(k.content, line.content) >= RESTATES))), None)
        if same is None:
            kept.append(line)
        else:
            out[n] = same
    return out


def cut_lines(ledger: list[dict[str, Any]]) -> int:
    """Memory lines (state, promises, facts, claims) a packet left out for its budget."""
    return sum(1 for e in ledger if e["kind"] in MEMORY_KINDS and e["why"] == "budget")


def fits_at(compile_at: Callable[[int], Compiled], budget: int) -> int | None:
    """The smallest budget above `budget`, in FIT_STEP steps up to FIT_CAP, at which no memory line is left
    out for the budget; None when even FIT_CAP leaves some out (ADR 0036). More room never places fewer
    lines, so this bisects."""
    lo, hi = budget // FIT_STEP + 1, FIT_CAP // FIT_STEP
    if lo > hi or cut_lines(compile_at(hi * FIT_STEP).ledger):
        return None
    while lo < hi:
        mid = (lo + hi) // 2
        if cut_lines(compile_at(mid * FIT_STEP).ledger):
            lo = mid + 1
        else:
            hi = mid
    return hi * FIT_STEP


def secret_text(holders: list[str], missing: list[str]) -> str:
    return f"Something known to {', '.join(holders) or 'someone'}, not known to {', '.join(missing)}."


def secret_line(holders: list[str], missing: list[str], turn: int | None) -> str:
    """Strict mode (ADR 0035): a line only some of the scene know, its content withheld."""
    return (f"    <Secret holders={quoteattr(', '.join(holders) or 'someone')} not_known_by={quoteattr(', '.join(missing))}"
            + (f' turn="{turn}"' if turn is not None else "") + f">{escape(secret_text(holders, missing))}</Secret>")


def compile_lines(ranked: list[Excerpt], budget_tokens: int, state: list[StateItem] | None = None,
                  threads: list[Line] | None = None, facts: list[Line] | None = None,
                  policy: str = DEFAULT_POLICY, lead: list[Line] | None = None, note: str = "") -> Compiled:
    """Fill the budget and record every offered line in a ledger (ADR 0027).

    Budget order is fixed: state, lead facts (how the cast stand with each other, ADR 0026), open threads
    (PHASE-7), facts and claims, excerpts. packet-v3 emits the kept threads and facts marked private in a
    <Private> section after Facts, and adds PRIVATE_NOTE (ADR 0034); earlier policies ignore the mark. packet-v4
    leaves out lines that say again what an earlier one says (`restated`, ADR 0036). `note`
    is added to the Note (a first-person narrator, ADR 0035) and counts as part of the frame. Lead facts open the Facts section, which the output keeps after
    Threads; excerpts are emitted in chronological order. packet-v0 fills them strictly in that order. packet-v1 and later skip excerpts that
    mostly restate an offered thread, fact or claim line (REPEATS), keeps room for the best-ranked
    remaining excerpt (EXCERPT_SHARE of the budget inside the frame; the excerpt is shortened to its best
    sentence, or cut, to fit) and cap parser state at STATE_SHARE. Costs use the policy's estimate (NON_ASCII). Returns an empty text when
    nothing fits or nothing is relevant; the ledger still lists what was offered."""
    if policy not in POLICIES:
        raise ValueError(f"unknown packet policy: {policy}")
    est = partial(estimate_tokens, non_ascii=NON_ASCII[policy])
    reserving = policy != "packet-v0"  # packet-v1 and later
    state, threads, facts, lead = state or [], threads or [], facts or [], lead or []
    ledger = ([_entry("state", {"key": i.key}, i.turn, f"{i.key}: {i.value}", i.value) for i in state]
              + [_entry(l.kind, l.ref, l.turn, l.text, l.content, l.marks) for l in lead + threads + facts]
              + [_entry("excerpt", {"revision": e.revision_id}, e.turn, e.text, e.text) for e in ranked])
    frame = [PACKET_OPEN, PACKET_NOTE.removesuffix("</Note>") + note + "</Note>", PACKET_CLOSE]
    used = est("\n".join(frame))
    if used >= budget_tokens:
        return Compiled("", 0, [], ledger)
    inner = budget_tokens - used
    repeats: dict[int, Line] = {}
    if reserving:
        for n, item in enumerate(ranked):
            if (same := _restates(item, lead + threads + facts)) is not None:
                repeats[n] = same
    first = next((n for n in range(len(ranked)) if n not in repeats), None)
    reserved: tuple[str, str] | None = None
    if reserving and first is not None:
        reserved = _fit_excerpt(ranked[first], int(inner * EXCERPT_SHARE), est)
    reserve = est(excerpt_line(ranked[first], reserved[1]) + "\n") if reserved else 0
    limit = budget_tokens - reserve  # what state, threads and facts may use
    state_cap = used + int(inner * STATE_SHARE) if reserving else budget_tokens

    kept_state: list[StateItem] = []
    for n, item in enumerate(state):
        extra = state_block(kept_state + [item])
        cost = est("\n".join(extra)) - est("\n".join(state_block(kept_state)))
        entry = ledger[n]
        entry["tok"] = cost
        if used + cost > min(limit, state_cap):
            entry["why"] = "state_cap" if used + cost <= limit else "budget"
            continue
        kept_state.append(item)
        used += cost
        entry["placed"], entry["why"] = True, "placed"
    extras: list[str] = []
    offset = len(state)
    privacy = policy in PRIVATE_POLICIES
    kept_private: list[str] = []
    folded = restated(lead + threads + facts) if policy in FOLD_POLICIES else {}

    def section(lines: list[Line], tag: str, opened: bool = False) -> list[str]:
        nonlocal used, offset
        kept: list[str] = []
        for line in lines:
            entry = ledger[offset]
            offset += 1
            if (same := folded.get(offset - 1 - len(state))) is not None:
                entry["why"], entry["restates"] = "restates", same.ref
                continue
            hidden = privacy and line.private
            if hidden:
                header = est("  <Private>\n  </Private>\n") if not kept_private else 0
            else:
                header = est(f"  <{tag}>\n  </{tag}>\n") if not kept and not opened else 0
            xml = line.private_xml or line.xml if hidden else line.xml
            cost = est(xml + "\n") + header
            needed = [text for mark, text in NOTE_EXTRAS if mark in xml and text not in extras]
            if hidden and PRIVATE_NOTE not in extras:
                needed.append(PRIVATE_NOTE)
            cost += sum(est(text) for text in needed)
            entry["tok"] = cost
            if hidden:
                entry["private"] = True
            if used + cost <= limit:
                (kept_private if hidden else kept).append(xml)
                extras.extend(needed)
                used += cost
                entry["placed"], entry["why"] = True, "placed"
        return kept

    kept_lead = section(lead, "Facts")
    kept_threads = section(threads, "Threads")
    kept_facts = kept_lead + section(facts, "Facts", opened=bool(kept_lead))
    chosen: list[tuple[Excerpt, str]] = []
    for n, item in enumerate(ranked):
        entry = ledger[offset + n]
        room = budget_tokens - used
        if n in repeats:
            entry["why"], entry["repeats"] = "repeats", repeats[n].ref
            continue
        if reserving:
            # The best excerpt had room kept for it; what the other sections left may fit more of it.
            fitted = _fit_excerpt(item, room, est)
            if fitted is None or (fitted[0] == "cut" and not (n == first and reserved)):  # only it is ever cut
                entry["tok"] = est(excerpt_line(item) + "\n")
                continue
            form, text = fitted
        else:
            form, text = "full", item.text
        cost = est(excerpt_line(item, text) + "\n")
        entry["tok"] = cost
        if used + cost > budget_tokens:
            continue
        chosen.append((item, text))
        used += cost
        entry["placed"], entry["why"] = True, "placed"
        if form != "full":
            entry["form"], entry["text"] = form, text[:400]
    if not chosen and not kept_state and not kept_facts and not kept_threads and not kept_private:
        return Compiled("", 0, [], ledger)
    chosen.sort(key=lambda c: c[0].turn)
    body = state_block(kept_state)
    if kept_threads:
        body += ["  <Threads>", *kept_threads, "  </Threads>"]
    if kept_facts:
        body += ["  <Facts>", *kept_facts, "  </Facts>"]
    if kept_private:
        body += ["  <Private>", *kept_private, "  </Private>"]
    body += [excerpt_line(e, t) for e, t in chosen]
    full_note = PACKET_NOTE.removesuffix("</Note>") + note + "".join(extras) + "</Note>"
    text = "\n".join([PACKET_OPEN, full_note, *body, PACKET_CLOSE])
    return Compiled(text, est(text), [e for e, _ in chosen], ledger)


def kept_counts(ledger: list[dict[str, Any]]) -> dict[str, int]:
    """How many state items, threads and fact lines (facts and claims) a packet kept (ADR 0026's trace
    fields), from its ledger."""
    placed = [e["kind"] for e in ledger if e["placed"]]
    return {"state": placed.count("state"), "threads": placed.count("thread"),
            "facts": placed.count("fact") + placed.count("claim")}


def compile_packet(ranked: list[Excerpt], budget_tokens: int, state: list[StateItem] | None = None,
                   facts: list[str] | None = None, threads: list[str] | None = None,
                   lead_facts: list[str] | None = None,
                   policy: str = "packet-v0") -> tuple[str, int, list[Excerpt], dict[str, int]]:
    """`compile_lines` for plain XML lines without provenance: (text, tokens, chosen excerpts, kept
    counts)."""
    def plain(kind: str, lines: list[str] | None) -> list[Line]:
        return [Line(kind, x, {}, None, x) for x in lines or []]

    out = compile_lines(ranked, budget_tokens, state, plain("thread", threads), plain("fact", facts), policy,
                        plain("fact", lead_facts))
    return out.text, out.tokens, out.excerpts, kept_counts(out.ledger)
