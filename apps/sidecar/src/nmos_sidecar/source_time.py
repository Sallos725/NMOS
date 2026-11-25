"""Literal clocks on recalled source revisions, never inferred event timestamps (PHASE-42)."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID
from xml.sax.saxutils import escape, quoteattr

import psycopg

from .packet import Compiled, Excerpt, NON_ASCII, PACKET_CLOSE, SOURCE_CLOCK_POLICIES, estimate_tokens

CUE = re.compile(r"언제|날짜|시각|시간|며칠째|며칠|몇\s*(?:년|월|일|시)|일차|무슨\s*요일|어느\s*날|무슨\s*계절|얼마나\s*지났"
                 r"|\b(?:when|date|time|day)\b", re.I)
# A clock key, as `statechange.scene_key` reads it (its last part under an entity: `Status.Date`, `World.시간`), and its
# category. Phase 42's `date` and `time` keep their keys; the other clock keys an RP status window uses have
# categories of their own, so a window that also has one of them keeps the date and time it gave before (a category
# with more than one key in a window is ambiguous and left out). `extraction.story_clock` reads `date` and `time` only.
KEYS = {"date": "date", "날짜": "date", "time": "time", "시간": "time", "시각": "time",
        "현재 시간": "now", "현재 시각": "now", "날짜/시간": "datetime", "일시": "datetime",
        "일차": "day", "day": "day", "요일": "weekday", "계절": "season"}
CATEGORIES = ("date", "time", "now", "datetime", "day", "weekday", "season")
# The same last part in SQL (parameter-free: no `%`): lower-cased and trimmed, everything to the last dot dropped.
BASE_SQL = r"btrim(regexp_replace(lower(btrim(st.key)), '^.*\.', ''))"
MAX_SOURCES = 2
MAX_VALUE = 160
TIMEOUT_MS = 25
NOTE = ("SourceTime is the literal status-window clock on the cited source, not necessarily the event's occurrence "
        "time. Do not date a flashback or infer elapsed time from it without explicit story evidence.")


@dataclass(frozen=True)
class Clock:
    revision: str
    turn: int
    rules_version: str
    fields: tuple[tuple[str, str, str], ...]  # original key, literal value, parser rule id

    def text(self) -> str:
        return "; ".join(f"{k}: {v}" for k, v, _ in self.fields)

    def xml(self) -> str:
        fields = "".join(f"<Field key={quoteattr(k)}>{escape(v)}</Field>" for k, v, _ in self.fields)
        return f'  <SourceTime turn="{self.turn}" source_revision={quoteattr(self.revision)}>{fields}</SourceTime>'


def base(key: str) -> str:
    """A status key's last part, lower-cased and trimmed (`Status.Date` → `date`), as BASE_SQL."""
    return key.strip().lower().rsplit(".", 1)[-1].strip()


def read(conn: psycopg.Connection, head: UUID, rules_version: str, revisions: list[str],
         upto: int | None, cut: int) -> dict[str, Clock]:
    if not revisions:
        return {}
    started = time.perf_counter()
    try:
        with conn.transaction():
            previous = int(conn.execute("SELECT setting FROM pg_settings WHERE name = 'statement_timeout'").fetchone()['setting'])
            allowance = min(previous, TIMEOUT_MS) if previous else TIMEOUT_MS
            conn.execute("SELECT set_config('statement_timeout', %s, true)", (f"{allowance}ms",))
            rows = conn.execute(
                "SELECT st.source_revision_id, st.key, st.value, st.rule_id, am.turn FROM state_observation st"
                " JOIN active_membership am ON am.source_revision_id = st.source_revision_id"
                " JOIN source_revision sr ON sr.id = st.source_revision_id"
                " WHERE am.commit_id = %s AND st.source_revision_id = ANY(%s::uuid[]) AND st.rules_version = %s"
                " AND am.position > %s AND am.position <= %s AND am.turn IS NOT NULL"
                " AND sr.lifecycle = 'accepted' AND coalesce(sr.metadata->>'disabled', '') NOT IN ('true', 'allBefore')"
                " AND coalesce(sr.metadata->>'isComment', 'false') <> 'true'"
                " AND " + BASE_SQL + " = ANY(%s) ORDER BY am.position, st.key, st.rule_id",
                (head, revisions, rules_version, cut, 2**31 - 1 if upto is None else upto, list(KEYS)),
            ).fetchall()
            conn.execute("SELECT set_config('statement_timeout', %s, true)", (str(previous),))
    except psycopg.errors.QueryCanceled:
        return {}
    if (time.perf_counter() - started) * 1000 > allowance:
        return {}
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row['source_revision_id']), []).append(row)
    out = {}
    for revision, entries in grouped.items():
        fields = []
        for category in CATEGORIES:
            candidates = [r for r in entries if KEYS.get(base(r['key'])) == category]
            # Multiple stored aliases are ambiguous here. The parser already resolved repeated exact keys
            # using its established last-match-wins rule; do not reinterpret that stored observation.
            if len(candidates) != 1:
                continue
            r = candidates[0]
            if r['value'].strip() and len(r['value']) <= MAX_VALUE:
                fields.append((r['key'], r['value'], r['rule_id']))
        if fields:
            out[revision] = Clock(revision, entries[0]['turn'], rules_version, tuple(fields))
    return out


def supplement(compiled: Compiled, ranked: list[Excerpt], clocks: dict[str, Clock],
               budget: int, policy: str) -> Compiled:
    """Use spare space only, after original selection; a missing clock never changes a chosen line."""
    if not compiled.text or not clocks or policy not in SOURCE_CLOCK_POLICIES:
        return compiled
    placed = {e.revision_id for e in compiled.excerpts}
    seen: set[str] = set()
    text = compiled.text
    tokens = compiled.tokens
    additions = []
    for item in ranked:
        revision = item.revision_id
        if revision in seen or revision not in placed or revision not in clocks:
            continue
        seen.add(revision)
        clock = clocks[revision]
        extra = (f'  <SourceTimeNote>{NOTE}</SourceTimeNote>\n' if not additions else '') + clock.xml() + '\n'
        candidate = text.removesuffix(PACKET_CLOSE) + extra + PACKET_CLOSE
        count = estimate_tokens(candidate, NON_ASCII[policy])
        if count > budget:
            continue
        additions.append({'kind': 'source_time', 'ref': {'revision': revision, 'rules_version': clock.rules_version},
                          'rules': sorted({r for _, _, r in clock.fields}),
                          'turn': clock.turn, 'text': clock.text(), 'tok': count - tokens,
                          'placed': True, 'why': 'placed', 'label': 'required'})
        text, tokens = candidate, count
        if len(additions) == MAX_SOURCES:
            break
    return Compiled(text, tokens, compiled.excerpts, compiled.ledger + additions)
