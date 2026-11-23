"""PHASE-60 S7, S8 (ADR 0086), A12: packet-v20's `happened` attribute and its `told` lines.

A line whose assertion has a `when_happened` carries `happened="…"` right after its `turn` (when it was told), and the
Note says which is which. Every other policy's packet is byte-identical. Synthetic names only (세라, 카이토, 하나, 유나).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg.rows import dict_row

from conftest import active_generation, make_client
from nmos_sidecar import packet, retrieval, scene
from nmos_sidecar.entities import resolve
from nmos_sidecar.facts import fact_entry, fact_line, served_assertions
from nmos_sidecar.packet import HAPPENED_MARK, HAPPENED_NOTE, HAPPENED_POLICIES, compile_lines
from nmos_sidecar.retrieval import Gathered, RecallOptions, cast_groups
from simchat import SimChat
from test_extract_v18 import USED, chat_of
from test_extract_v19 import SCENE, event_row, told_row
from test_extract_v19_read import retrieve
from test_extraction import drain, filler
from test_generations import LLM, conv_id
from test_semantics import row
from test_sidecar_integration import sync

C = {"subject_type": "character"}
V20 = RecallOptions(policy="packet-v20")


def event(pos: int, who: str, value: str, **kw) -> dict:
    return row(pos, who, "event", None, value, **C, **kw)


# --- happened: the line (pure) -----------------------------------------------------------------------------------------


def test_the_policy_sets_hold_packet_v20_only():
    assert HAPPENED_POLICIES == frozenset({"packet-v20"})
    assert HAPPENED_MARK not in HAPPENED_NOTE  # the Note's sentence never counts as a marked line


def test_a_fact_line_carries_happened_right_after_its_turn_only_when_asked():
    f = event(8, "유나", "성을 떠났다", when_happened="어제")
    assert fact_line(f) == '    <Fact kind="event" turn="8">유나 event: 성을 떠났다</Fact>'
    assert fact_line(f, happened=True) == '    <Fact kind="event" turn="8" happened="어제">유나 event: 성을 떠났다</Fact>'
    marked = {**f, "knowledge": "limited", "known_by": ["세라"], "hidden_from": ["하나"], "polarity": "negative"}
    assert fact_line(marked, happened=True) == (
        '    <Fact kind="event" turn="8" happened="어제" negated="true" known_by="세라" hidden_from="하나">'
        '유나 event: 성을 떠났다</Fact>')


def test_no_attribute_without_a_value():
    for f in (event(8, "유나", "성을 떠났다"), event(8, "유나", "성을 떠났다", when_happened=""),
              event(8, "유나", "성을 떠났다", when_happened=None)):
        assert fact_line(f, happened=True) == fact_line(f)
        assert fact_entry(f, happened=True) == fact_entry(f)


def test_the_value_is_escaped_inside_double_quotes():
    f = event(8, "유나", "성을 떠났다", when_happened='그 "날" & <밤>')
    assert ' happened="그 &quot;날&quot; &amp; &lt;밤&gt;"' in fact_line(f, happened=True)
    assert HAPPENED_MARK in fact_line(f, happened=True)  # double quotes always: the Note's mark matches


def test_the_entry_keeps_its_ledger_text_and_content():
    f = event(8, "유나", "성을 떠났다", when_happened="어제")
    with_it, without = fact_entry(f, happened=True), fact_entry(f)
    assert with_it.xml != without.xml
    assert (with_it.text, with_it.content, with_it.ref, with_it.turn, with_it.marks) == (
        without.text, without.content, without.ref, without.turn, without.marks)


def test_the_note_says_which_is_which_only_under_v20_and_only_when_a_line_carries_it():
    f = event(8, "유나", "성을 떠났다", when_happened="어제")
    out = compile_lines([], 2000, facts=[fact_entry(f, happened=True)], policy="packet-v20")
    assert '<Fact kind="event" turn="8" happened="어제">' in out.text and HAPPENED_NOTE in out.text
    plain = compile_lines([], 2000, facts=[fact_entry(event(8, "유나", "성을 떠났다"), happened=True)],
                          policy="packet-v20")
    assert HAPPENED_NOTE not in plain.text and HAPPENED_MARK not in plain.text
    # an older policy never adds the sentence, even for a line that spells the mark
    odd = packet.Line("fact", f'    <Fact kind="has_trait" turn="4">하나 has trait:{HAPPENED_MARK}x"</Fact>',
                      {"assertion": "o"}, 4, "x", "x")
    assert HAPPENED_NOTE not in compile_lines([], 2000, facts=[odd], policy="packet-v19").text


def test_cast_and_gone_lines_carry_it_under_v20_only():
    """Every fact line the packet emits: a cast line and a gone line too (their predicates rarely have one)."""
    rows = [row(10, "세라", "has_status", None, "사망", **C, when_happened="지난밤"), event(19, "카이토", "들어왔다")]
    view = {"facts": rows, "claims": [], "other": [], "excluded": {}, "threads": []}
    r = resolve(uuid.uuid4(), rows)
    cast = scene.cast(rows, r, "세라는?", "", 20)
    for policy, attr in (("packet-v20", True), ("packet-v19", False)):
        options = RecallOptions(policy=policy)
        groups, _ = cast_groups(view, cast, r, "세라는?", options)
        xml = "".join(line.xml for _, lines in groups for line in lines)
        assert ('happened="지난밤"' in xml) is attr
    [gone] = retrieval.gone_lines(view, r, cast, 20, V20)
    assert '<Fact kind="has_status" turn="10" happened="지난밤" gone="true">' in gone.xml


def test_an_echoed_happened_line_is_dropped_by_the_normalizer():
    """A12 / K27: the attribute sits inside <Fact>, so clean-v3 drops an echo whole."""
    xml = fact_line(event(8, "유나", "성을 떠났다", when_happened="어제"), happened=True).strip()
    cleaned = packet.clean_text(f"카이토가 고개를 숙였다. {xml} 바람이 분다.")
    assert cleaned == "카이토가 고개를 숙였다. 바람이 분다."


# --- end to end (stub model, test database) --------------------------------------------------------------------------


QUESTION = "세라가 카이토에게 유나에 대해 무슨 말을 했지?"
EVENT_V20 = '<Fact kind="event" turn="8" happened="어제">유나 event: 성을 떠났다</Fact>'
EVENT_PLAIN = '<Fact kind="event" turn="8">유나 event: 성을 떠났다</Fact>'


def complete(system, user):
    """The model: for SCENE (turn 8), the told row (세라 → 카이토, kept from 하나) and the event, which happened 어제."""
    target = user.split("TARGET turn", 1)[1] if "TARGET turn" in user else ""
    if SCENE in target:
        return {"assertions": [told_row(), event_row(when_happened="어제")]}, "{}", USED
    return {"assertions": []}, "{}", USED


@contextmanager
def extracted(url: str, **settings: Any) -> Iterator[tuple[Any, SimChat]]:
    """SCENE told at turn 8, then 8 more turns, so its message is out of the prompt's window; extract-v19 by the stub."""
    chat = chat_of(*[f"평범한 하루 {i}." for i in range(8)], SCENE)
    filler(chat, 8)
    with make_client(url, **LLM, extract_compiler="extract-v19", **settings) as client:
        sync(client, chat)
        drain(url, complete)
        yield client, chat


def served(url: str, client, chat: SimChat) -> list[dict]:
    with psycopg.connect(url, row_factory=dict_row) as conn:
        head = conn.execute("SELECT head_commit_id FROM conversation WHERE id = %s",
                            (conv_id(client, chat),)).fetchone()["head_commit_id"]
        return served_assertions(conn, head, active_generation(conn, "extract").key)


def forget_when(url: str) -> None:
    with psycopg.connect(url, autocommit=True) as conn:
        assert conn.execute("UPDATE assertion SET when_happened = NULL WHERE when_happened IS NOT NULL").rowcount == 1


def test_v20_shows_when_it_happened_beside_when_it_was_told(migrated):
    with extracted(migrated, packet_policy="packet-v20") as (client, chat):
        [ev] = [a for a in served(migrated, client, chat) if a["predicate"] == "event"]
        assert (ev["turn"], ev["when_happened"]) == (8, "어제")
        out = retrieve(client, chat, QUESTION)
        forget_when(migrated)
        plain = retrieve(client, chat, QUESTION)
    assert out["policy"] == "packet-v20"
    assert EVENT_V20 in out["text"] and HAPPENED_NOTE in out["text"]
    assert out["text"].count(HAPPENED_MARK) == 1
    assert EVENT_PLAIN in plain["text"] and HAPPENED_NOTE not in plain["text"] and HAPPENED_MARK not in plain["text"]


def test_v19_is_byte_identical_with_or_without_when_happened(migrated):
    with extracted(migrated) as (client, chat):
        out = retrieve(client, chat, QUESTION)
        forget_when(migrated)
        plain = retrieve(client, chat, QUESTION)
    assert out["policy"] == plain["policy"] == "packet-v19"
    assert EVENT_PLAIN in out["text"] and HAPPENED_MARK not in out["text"] and HAPPENED_NOTE not in out["text"]
    assert out["text"] == plain["text"]
