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
from nmos_sidecar import facts as F, packet, retrieval, scene, threads
from nmos_sidecar.entities import resolve
from nmos_sidecar.facts import (_annotate, fact_entry, fact_line, memory_view, served_assertions, settled_entry,
                                settled_line, thread_entry, thread_line, told_entry)
from nmos_sidecar.packet import (HAPPENED_MARK, HAPPENED_NOTE, HAPPENED_POLICIES, TOLD_MARK, TOLD_NOTE, TOLD_POLICIES,
                                 compile_lines)
from nmos_sidecar.retrieval import TOLD_MAX, Gathered, RecallOptions, cast_groups
from nmos_sidecar.secrets import fold as fold_secrets
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
    assert HAPPENED_POLICIES == TOLD_POLICIES == frozenset({"packet-v20"})
    assert HAPPENED_MARK not in HAPPENED_NOTE  # the Note's sentence never counts as a marked line
    assert TOLD_MARK not in TOLD_NOTE and TOLD_MAX == 2


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


# --- happened on a promise's thread (pure) -------------------------------------------------------------------------------


PROMISE = "다시 돌아오겠다"


def promised(pos: int, **kw) -> dict:
    return row(pos, "세라", "promised", "카이토", PROMISE, subject_type="character", object_type="character", **kw)


def test_fold_carries_when_happened_from_the_opening_assertion():
    [t], _, _ = threads.fold([promised(3, when_happened="다음 보름날"), promised(5, when_happened="내일")])
    assert t["when_happened"] == "다음 보름날" and t["restated"] == [{"turn": 5, "position": 5}]
    [t], _, _ = threads.fold([promised(3), promised(5, when_happened="내일")])
    assert t["when_happened"] is None  # the opening one has none; a restatement adds nothing


def test_a_promise_thread_line_carries_happened_after_its_turn_only_when_asked():
    [t], _, _ = threads.fold([promised(8, when_happened="다음 보름날")])
    assert thread_line(t) == '    <Thread kind="promise" by="세라" to="카이토" turn="8">다시 돌아오겠다</Thread>'
    assert thread_line(t, happened=True) == (
        '    <Thread kind="promise" by="세라" to="카이토" turn="8" happened="다음 보름날">다시 돌아오겠다</Thread>')
    [kept], _, _ = threads.fold([promised(8, when_happened="다음 보름날"),
                                 row(12, "세라", "fulfilled", None, PROMISE, subject_type="character")])
    assert settled_line(kept, happened=True) == (
        '    <Thread status="kept" kind="promise" by="세라" to="카이토" turn="8" happened="다음 보름날" closed_turn="12">'
        '다시 돌아오겠다</Thread>')
    assert thread_entry(t, happened=True).text == thread_entry(t).text
    assert settled_entry(kept, happened=True).text == settled_entry(kept).text
    [plain], _, _ = threads.fold([promised(8)])
    assert thread_line(plain, happened=True) == thread_line(plain)


def test_the_thread_note_and_happened_note_both_under_v20():
    [t], _, _ = threads.fold([promised(8, when_happened="다음 보름날")])
    out = compile_lines([], 2000, threads=[thread_entry(t, happened=True)], policy="packet-v20")
    assert 'turn="8" happened="다음 보름날">' in out.text and HAPPENED_NOTE in out.text


def test_an_echoed_happened_thread_line_is_dropped_by_the_normalizer():
    [t], _, _ = threads.fold([promised(8, when_happened="다음 보름날")])
    cleaned = packet.clean_text(f"카이토가 웃었다. {thread_line(t, happened=True).strip()} 바람이 분다.")
    assert cleaned == "카이토가 웃었다. 바람이 분다."


# --- told: selection, gate and modes (pure) ----------------------------------------------------------------------------


MARKS = {"knowledge": "limited", "known_by": ["세라", "카이토"], "hidden_from": ["하나"]}


def told(pos: int, teller: str, hearer: str, value: str, about: tuple[str, ...] = (), **kw) -> dict:
    return row(pos, teller, "told", hearer, value, subject_type="character", object_type="character",
               participants=tuple({"name": n, "type": "character"} for n in about), compiler="extract-v19", **kw)


def told_scene(rows: list[dict], query: str, others: list[dict] = (), secret_rows: list[dict] = (),
               options: RecallOptions = V20, in_context: frozenset[str] = frozenset(), now: int = 20,
               ) -> tuple[Gathered, list[packet.Line]]:
    """`retrieval.told_lines` as gather calls it: the scene from the view's own rows (never the told rows)."""
    base = list(others) + list(secret_rows)
    r = resolve(uuid.uuid4(), base + rows)
    for x in base + rows:
        _annotate(x, r)
    secrets, _, _ = fold_secrets(list(secret_rows), r)
    view = {"facts": base, "claims": [], "other": [], "excluded": {}, "threads": [], "told": rows, "secrets": secrets}
    g = Gathered()
    g.cast = scene.cast(base, r, query, "", now)
    return g, retrieval.told_lines(g, view, r, query, "", set(in_context), options)


def test_a_told_line_for_a_message_that_names_the_teller():
    g, lines = told_scene([told(8, "세라", "카이토", "유나가 왕녀라는 사실", about=("유나",))], "세라는 뭐라고 했어?")
    [line] = lines
    assert line.xml == '    <Fact kind="told" turn="8">세라 told 카이토: 유나가 왕녀라는 사실; about: 유나</Fact>'
    assert (line.kind, line.ref, line.turn, line.content) == ("fact", {"assertion": 8}, 8, "유나가 왕녀라는 사실")
    assert line.text == "세라 told 카이토: 유나가 왕녀라는 사실; about: 유나"


def test_the_hearer_named_or_either_one_in_the_scene_brings_it_too():
    rows = [told(8, "세라", "카이토", "열쇠를 숨긴 곳")]
    assert len(told_scene(rows, "카이토한테 물어볼까")[1]) == 1
    # not named: 카이토 is in the scene (a row of the last turns names him)
    assert len(told_scene(rows, "오늘은 날씨가 맑네.", others=[event(19, "카이토", "들어왔다")])[1]) == 1


def test_none_when_neither_is_named_or_in_the_scene():
    rows = [told(8, "세라", "카이토", "열쇠를 숨긴 곳", about=("유나",))]
    assert told_scene(rows, "오늘은 날씨가 맑네.", others=[event(19, "하나", "들어왔다")])[1] == []
    assert told_scene(rows, "유나는 어디 있지?")[1] == []  # whom it is about is not the teller or the hearer
    # the persona is in every scene, so it brings none by itself
    assert told_scene([told(8, "{{user}}", "레오", "열쇠를 숨긴 곳")], "오늘은 날씨가 맑네.")[1] == []


def test_at_most_two_ranked_as_facts_are():
    rows = [told(i, "세라", "카이토", f"소식 {i}") for i in (3, 5, 7, 9)]
    _, lines = told_scene(rows, "세라가 카이토에게 소식 3 얘기를 했지?")
    assert len(lines) == TOLD_MAX == 2
    assert [line.turn for line in lines] == [3, 9]  # the one the words point at, then the newest


def test_a_told_line_whose_message_is_in_the_prompt_is_not_said_again():
    rows = [told(8, "세라", "카이토", "열쇠를 숨긴 곳")]
    assert told_scene(rows, "세라는?", in_context=frozenset({"m8"}))[1] == []
    assert told_scene(rows, "오늘은 맑네", others=[event(19, "카이토", "들어왔다")], in_context=frozenset({"m8"}))[1] == []


def test_older_policies_offer_none():
    rows = [told(8, "세라", "카이토", "열쇠를 숨긴 곳")]
    for policy in ("packet-v19", "packet-v14", "packet-v8"):
        assert told_scene(rows, "세라는?", options=RecallOptions(policy=policy))[1] == []


SECRET = row(5, "세라", "knows", None, "유나는 사실 왕녀다", **C, **MARKS)


def test_a_told_line_that_says_a_secret_kept_from_someone_in_the_scene_is_left_out_and_logged():
    """D62: as an excerpt would be. The told row itself is unmarked: only the secret it repeats keeps it out."""
    rows = [told(8, "세라", "카이토", "유나가 사실 왕녀라는 것")]
    here = [event(19, "하나", "들어왔다")]
    g, lines = told_scene(rows, "세라가 카이토에게 뭐라고 했어?", others=here, secret_rows=[SECRET])
    assert lines == []
    out = retrieval.compile_gathered(g, 2000, "packet-v20")
    assert "왕녀" not in out.text
    [hidden] = [e for e in out.ledger if e.get("label") == "hidden"]
    assert hidden == {"kind": "fact", "ref": {"assertion": 8}, "turn": 8, "text": "", "tok": 0, "placed": False,
                      "why": "secret_gate", "label": "hidden"}
    # another told line of the same pair that says no secret is offered
    other = told(9, "세라", "카이토", "내일 비가 온다는 소식")
    _, lines = told_scene(rows + [other], "세라가 카이토에게 뭐라고 했어?", others=here, secret_rows=[SECRET])
    assert [line.ref for line in lines] == [{"assertion": 9}]


def test_a_gated_line_frees_no_more_than_the_cap():
    rows = [told(8, "세라", "카이토", "유나가 사실 왕녀라는 것")] + [told(i, "세라", "카이토", f"소식 {i}") for i in (10, 11, 12)]
    _, lines = told_scene(rows, "세라는?", others=[event(19, "하나", "들어왔다")], secret_rows=[SECRET])
    assert len(lines) == 2 and {"assertion": 8} not in [line.ref for line in lines]


def kept_from_hana() -> list[dict]:
    """A told line only 세라 and 카이토 know, with 하나 in the scene."""
    return [told(8, "세라", "카이토", "열쇠를 숨긴 곳", **MARKS)]


def test_a_told_line_some_of_the_scene_do_not_know_is_private():
    g, [line] = told_scene(kept_from_hana(), "세라는?", others=[event(19, "하나", "들어왔다")])
    assert line.private
    out = retrieval.compile_gathered(Gathered(cast=g.cast, facts=[line]), 2000, "packet-v20")
    private = out.text.split("<Private>", 1)[1].split("</Private>", 1)[0]
    assert ('<Fact kind="told" turn="8" known_by="세라, 카이토" hidden_from="하나">세라 told 카이토: 열쇠를 숨긴 곳</Fact>'
            in private)
    assert TOLD_NOTE in out.text and packet.PRIVATE_NOTE in out.text


def test_strict_mode_withholds_it_as_a_secret():
    strict = RecallOptions(policy="packet-v20", strict=True)
    g, lines = told_scene(kept_from_hana(), "세라는?", others=[event(19, "하나", "들어왔다")], options=strict)
    assert [line.kind for line in lines] == ["secret"] and g.withheld == 1
    out = retrieval.compile_gathered(Gathered(cast=g.cast, facts=lines), 2000, "packet-v20")
    assert "<Secret " in out.text and "열쇠" not in out.text and TOLD_NOTE not in out.text


def test_a_narrator_who_does_not_know_it_never_sees_it():
    here = [event(19, "하나", "들어왔다")]
    g, lines = told_scene(kept_from_hana(), "세라는?", others=here,
                          options=RecallOptions(policy="packet-v20", narrator="하나"))
    assert lines == [] and g.withheld == 1
    _, lines = told_scene(kept_from_hana(), "세라는?", others=here,
                          options=RecallOptions(policy="packet-v20", narrator="카이토"))
    assert len(lines) == 1  # the hearer is shown to know it


def test_the_told_note_only_under_v20_and_only_when_a_line_carries_it():
    line = told_entry(told(8, "세라", "카이토", "열쇠를 숨긴 곳"))
    assert TOLD_NOTE in compile_lines([], 2000, facts=[line], policy="packet-v20").text
    assert TOLD_NOTE not in compile_lines([], 2000, facts=[line], policy="packet-v19").text
    plain = fact_entry(event(8, "유나", "성을 떠났다"))
    assert TOLD_NOTE not in compile_lines([], 2000, facts=[plain], policy="packet-v20").text


def test_a_told_line_carries_happened_like_any_fact_line():
    line = told_entry(told(8, "세라", "카이토", "열쇠를 숨긴 곳", when_happened="어제"), happened=True)
    assert line.xml.startswith('    <Fact kind="told" turn="8" happened="어제">')


def test_an_echoed_told_line_is_dropped_by_the_normalizer():
    """A12 / K27: a told line is a <Fact>, so clean-v3 drops an echo whole."""
    xml = told_entry(told(8, "세라", "카이토", "유나가 왕녀라는 사실", about=("유나",), **MARKS)).xml.strip()
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
def extracted(url: str, story: str = SCENE, stub: Any = None, **settings: Any) -> Iterator[tuple[Any, SimChat]]:
    """`story` told at turn 8, then 8 more turns, so its message is out of the prompt's window; extract-v19 by the
    stub (`complete` by default)."""
    chat = chat_of(*[f"평범한 하루 {i}." for i in range(8)], story)
    filler(chat, 8)
    with make_client(url, **LLM, extract_compiler="extract-v19", **settings) as client:
        sync(client, chat)
        drain(url, stub or complete)
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


TOLD_XML = ('<Fact kind="told" turn="8" known_by="세라, 카이토" hidden_from="하나">'
            '세라 told 카이토: 유나가 왕녀라는 사실; about: 유나</Fact>')


def test_v20_offers_the_told_line_when_the_message_names_the_teller_and_none_otherwise(migrated):
    with extracted(migrated, packet_policy="packet-v20") as (client, chat):
        named = retrieve(client, chat, QUESTION)
        unnamed = retrieve(client, chat, "오늘은 날씨가 맑네.")
    assert TOLD_XML in named["text"] and TOLD_NOTE in named["text"]
    private = named["text"].split("<Private>", 1)[1].split("</Private>", 1)[0]
    assert TOLD_XML in private  # 유나 and the persona are in the scene and are not shown to know it
    assert TOLD_MARK not in unnamed["text"] and TOLD_NOTE not in unnamed["text"]


def test_a_told_row_stored_by_extract_v19_is_in_no_v19_packet(migrated):
    with extracted(migrated) as (client, chat):
        assert [a for a in served(migrated, client, chat) if a["predicate"] == "told"]
        out = retrieve(client, chat, QUESTION)
    assert out["policy"] == "packet-v19"
    assert TOLD_MARK not in out["text"] and "왕녀라는 사실;" not in out["text"] and TOLD_NOTE not in out["text"]


def test_memory_view_reads_told_only_when_asked_and_its_facts_do_not_change(migrated):
    with extracted(migrated) as (client, chat):
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            head = conn.execute("SELECT head_commit_id FROM conversation WHERE id = %s",
                                (conv_id(client, chat),)).fetchone()["head_commit_id"]
            key = active_generation(conn, "extract").key
            plain, asked = memory_view(conn, head, key), memory_view(conn, head, key, told=True)
    assert "told" not in plain
    [t] = asked["told"]
    assert (t["subject"], t["object"], t["predicate"]) == ("세라", "카이토", "told")
    # annotated by the view's own resolution, which told rows never shape: 세라 and 카이토 appear in no other row here,
    # so they stay unresolved names (and 유나, the event's subject, is an entity)
    assert "subject_entity" in t and "id" not in t["subject_entity"]
    assert {"세라", "카이토", "유나"} <= set(t["names"])
    assert all(e["name"] != "세라" for e in plain["entities"])
    assert {k: v for k, v in asked.items() if k not in ("told", "resolution")} == {
        k: v for k, v in plain.items() if k != "resolution"}


PROMISE_SCENE = "세라는 카이토에게 다음 보름날 다시 돌아오겠다고 약속했다. 하나는 웃었다."
PROMISE_QUOTE = "다시 돌아오겠다고 약속했다"
WHEN_QUESTION = "세라는 언제 돌아온다고 했지?"
THREAD_V20 = '<Thread kind="promise" by="세라" to="카이토" turn="8" happened="다음 보름날">다시 돌아오겠다</Thread>'
THREAD_PLAIN = '<Thread kind="promise" by="세라" to="카이토" turn="8">다시 돌아오겠다</Thread>'


def promise_stub(system, user):
    """The model: for PROMISE_SCENE (turn 8), 세라's promise to 카이토, set for 다음 보름날, and 하나 at the scene."""
    target = user.split("TARGET turn", 1)[1] if "TARGET turn" in user else ""
    if PROMISE_SCENE in target:
        actual = {"polarity": "positive", "modality": "actual", "source": "narration"}
        return {"assertions": [
            {"subject": "세라", "subject_type": "character", "predicate": "promised", "object": "카이토",
             "object_type": "character", "value": PROMISE, "when_happened": "다음 보름날", **actual,
             "evidence": PROMISE_QUOTE},
            {"subject": "하나", "subject_type": "character", "predicate": "event", "value": "웃었다", **actual,
             "evidence": "하나는 웃었다"}]}, "{}", USED
    return {"assertions": []}, "{}", USED


def test_v20_shows_when_a_promise_is_for_on_its_thread(migrated):
    with extracted(migrated, PROMISE_SCENE, promise_stub, packet_policy="packet-v20") as (client, chat):
        out = retrieve(client, chat, WHEN_QUESTION)
        forget_when(migrated)
        plain = retrieve(client, chat, WHEN_QUESTION)
    assert THREAD_V20 in out["text"] and HAPPENED_NOTE in out["text"]
    assert THREAD_PLAIN in plain["text"] and HAPPENED_MARK not in plain["text"] and HAPPENED_NOTE not in plain["text"]


def test_v19_threads_are_byte_identical_with_or_without_when_happened(migrated):
    with extracted(migrated, PROMISE_SCENE, promise_stub) as (client, chat):
        out = retrieve(client, chat, WHEN_QUESTION)
        forget_when(migrated)
        plain = retrieve(client, chat, WHEN_QUESTION)
    assert THREAD_PLAIN in out["text"] and HAPPENED_MARK not in out["text"]
    assert out["text"] == plain["text"]


def test_the_new_thread_key_changes_no_page_of_a_chat_without_when_happened(migrated, monkeypatch):
    """The Inspector's chat and person pages and the panel's memory, person and map screens are the same whether
    `threads.fold` adds `when_happened` or not (as before it did), for a chat with none."""
    with extracted(migrated, PROMISE_SCENE, promise_stub) as (client, chat):
        forget_when(migrated)
        conv = conv_id(client, chat)
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            head = conn.execute("SELECT head_commit_id FROM conversation WHERE id = %s", (conv,)).fetchone()[
                "head_commit_id"]
            view = memory_view(conn, head, active_generation(conn, "extract").key)
        [t] = view["threads"]
        assert "when_happened" in t and t["when_happened"] is None
        sera = next(e["id"] for e in view["entities"] if e["name"] == "세라")
        urls = [f"/v1/inspector/c/{conv}", f"/v1/inspector/c/{conv}/e/{sera}", f"/v1/views/c/{conv}/memory",
                f"/v1/views/c/{conv}/person/{sera}", f"/v1/views/c/{conv}/map", f"/v1/views/c/{conv}/map/graph"]
        now = [client.get(u) for u in urls]
        fold = F.fold_threads

        def before(*args, **kw):  # threads.fold as it was: no when_happened key
            out, unmatched, used = fold(*args, **kw)
            for th in out:
                th.pop("when_happened", None)
            return out, unmatched, used

        monkeypatch.setattr(F, "fold_threads", before)
        then = [client.get(u) for u in urls]
    for u, a, b in zip(urls, now, then):
        assert a.status_code == b.status_code == 200, u
        assert a.content == b.content, u


# --- told on the pages' data (api.py; the renderers are another track's) ----------------------------------------------


def chain_stub(system, user):
    """`complete` plus rows that make 세라 and 카이토 entities of the chat (a told row never resolves anyone)."""
    out, raw, used = complete(system, user)
    target = user.split("TARGET turn", 1)[1] if "TARGET turn" in user else ""
    if SCENE in target:
        actual = {"polarity": "positive", "modality": "actual", "source": "narration"}
        out["assertions"] += [
            {"subject": "세라", "subject_type": "character", "predicate": "event", "value": "비밀을 털어놓았다",
             **actual, "evidence": "유나가 왕녀라는 사실을 조용히 털어놓았다"},
            {"subject": "하나", "subject_type": "character", "predicate": "feels_toward", "object": "카이토",
             "object_type": "character", "value": "고마움", **actual, "evidence": "고마운 마음이 가득했지만"}]
    return out, raw, used


def page_data(client, monkeypatch, conv: str, who: dict[str, str]) -> dict[str, Any]:
    """What api.py hands the renderers: the person sheet and the Inspector person page of each of `who`
    ({name: entity id}), and the memory map; each renderer captured, not drawn."""
    from nmos_sidecar import inspector, views
    got: dict[str, Any] = {}
    monkeypatch.setattr(views, "person", lambda data, *a, **k: got.__setitem__(("person", data["entity"]["id"]), data)
                        or "")
    monkeypatch.setattr(views, "memory_map", lambda data, *a, **k: got.__setitem__("map", data) or "")
    monkeypatch.setattr(inspector, "character", lambda conv_, eid, view, *a, **k: got.__setitem__(("page", eid), view)
                        or "")
    for eid in who.values():
        assert client.get(f"/v1/views/c/{conv}/person/{eid}").status_code == 200
        assert client.get(f"/v1/inspector/c/{conv}/e/{eid}").status_code == 200
    assert client.get(f"/v1/views/c/{conv}/map").status_code == 200
    monkeypatch.undo()
    return got


def chain_chat(url: str, client, chat: SimChat) -> tuple[str, dict[str, str]]:
    conv = str(conv_id(client, chat))
    with psycopg.connect(url, row_factory=dict_row) as conn:
        head = conn.execute("SELECT head_commit_id FROM conversation WHERE id = %s", (conv,)).fetchone()["head_commit_id"]
        view = memory_view(conn, head, active_generation(conn, "extract").key)
    ids = {e["name"]: str(e["id"]) for e in view["entities"] if e["type"] == "character"}
    return conv, {n: ids[n] for n in ("세라", "카이토", "하나")}


TOLD_ROW_KEYS = {"id", "turn", "position", "subject", "object", "value", "participants", "knowledge", "known_by",
                 "hidden_from", "subject_entity", "object_entity", "evidence"}


def test_the_pages_get_the_told_rows_of_the_person_and_the_map_all_of_them(migrated, monkeypatch):
    with extracted(migrated, stub=chain_stub) as (client, chat):
        conv, who = chain_chat(migrated, client, chat)
        got = page_data(client, monkeypatch, conv, who)
    for name in ("세라", "카이토"):  # teller and hearer
        [t] = got[("person", who[name])]["told"]
        assert set(t) == TOLD_ROW_KEYS
        assert (t["subject"], t["object"], t["value"], t["turn"]) == ("세라", "카이토", "유나가 왕녀라는 사실", 8)
        assert t["participants"] == [{"name": "유나", "type": "character"}]
        assert (t["knowledge"], t["known_by"], t["hidden_from"]) == ("limited", ["세라", "카이토"], ["하나"])
        assert t["subject_entity"]["id"] == who["세라"] and t["object_entity"]["id"] == who["카이토"]
        assert [x["id"] for x in got[("page", who[name])]["told"]] == [t["id"]]
    assert "told" not in got[("person", who["하나"])] and "told" not in got[("page", who["하나"])]  # neither end
    assert [x["subject"] for x in got["map"]["told"]] == ["세라"]


def test_without_told_rows_the_pages_and_their_data_are_as_before(migrated, monkeypatch):
    with extracted(migrated, stub=chain_stub) as (client, chat):
        conv, who = chain_chat(migrated, client, chat)
        urls = [f"/v1/views/c/{conv}/person/{who['세라']}", f"/v1/inspector/c/{conv}/e/{who['세라']}",
                f"/v1/views/c/{conv}/map", f"/v1/views/c/{conv}/map/graph", f"/v1/views/c/{conv}/memory"]
        with_rows = [client.get(u).content for u in urls]
        with psycopg.connect(migrated, autocommit=True) as conn:
            assert conn.execute("DELETE FROM assertion WHERE predicate = 'told'").rowcount == 1
        without = [client.get(u).content for u in urls]
        got = page_data(client, monkeypatch, conv, who)
    assert with_rows == without  # nothing drawn from them yet, and nothing else moved
    assert all("told" not in data for data in got.values())


def test_a_told_row_whose_teller_or_hearer_is_left_out_is_dropped_as_a_pair_is(migrated, monkeypatch):
    with extracted(migrated, stub=chain_stub) as (client, chat):
        conv, who = chain_chat(migrated, client, chat)
        preview = client.post(f"/v1/conversations/{conv}/repairs/preview",
                              json={"kind": "entity_exclude", "item": "카이토"}).json()
        done = client.post(f"/v1/conversations/{conv}/repairs", json={
            "kind": "entity_exclude", "item": "카이토", "scope": "cast", "expect": preview["fingerprint"]})
        assert done.status_code == 200, done.text
        got = page_data(client, monkeypatch, conv, who)
    assert "told" not in got[("person", who["세라"])] and "told" not in got["map"]


def test_strict_and_narrator_change_the_told_data_no_more_than_the_facts(migrated, monkeypatch):
    """The pages are the owner's view: the memory modes are the packet's (ADR 0035), for facts and told rows alike."""
    with extracted(migrated, stub=chain_stub) as (client, chat):
        conv, who = chain_chat(migrated, client, chat)
        plain = page_data(client, monkeypatch, conv, who)
        modes = []
        for mode in ({"strict": True}, {"strict": False, "narrator": "하나"}):
            assert client.put(f"/v1/conversations/{conv}/memory-mode", json=mode).status_code == 200
            modes.append(page_data(client, monkeypatch, conv, who))
    for data in modes:
        for k in plain:
            assert data[k].get("told") == plain[k].get("told"), k
    assert plain[("person", who["세라"])]["told"]


# --- a v20 request with a placed told line and a gated one: replay and the pages read its trace ------------------------


SECRET_VALUE = "유나가 왕녀라는 사실"
PLAIN_TOLD = "하나가 그 자리에 없었다는 것"


def gate_stub(system, user):
    """The model: a secret 세라 and 카이토 keep from 하나, a told row that repeats it (unmarked) and another that does
    not, both 세라 → 카이토."""
    target = user.split("TARGET turn", 1)[1] if "TARGET turn" in user else ""
    if SCENE in target:
        actual = {"polarity": "positive", "modality": "actual", "source": "narration"}
        unmarked = {"knowledge": None, "known_by": None, "hidden_from": None}
        return {"assertions": [
            {"subject": "세라", "subject_type": "character", "predicate": "knows", "value": SECRET_VALUE, **actual,
             "knowledge": "limited", "known_by": ["세라", "카이토"], "hidden_from": ["하나"],
             "evidence": "유나가 왕녀라는 사실을 조용히 털어놓았다"},
            told_row(**unmarked),
            told_row(value=PLAIN_TOLD, evidence="하나는 그 자리에 없었다", **unmarked)]}, "{}", USED
    return {"assertions": []}, "{}", USED


def test_a_v20_trace_with_told_lines_replays_and_the_pages_read_it(migrated):
    from uuid import UUID

    from nmos_sidecar import audit
    with extracted(migrated, stub=gate_stub, packet_policy="packet-v20") as (client, chat):
        query = "하나야, 세라가 카이토에게 뭐라고 했지?"
        chat.user(query)
        sync(client, chat)
        out = client.post("/v1/retrieve", json={
            "chat_id": chat.id, "query": query, "previous_ai": "", "budget_tokens": 2000,
            "in_context_ids": [m["chatId"] for m in chat.messages[-6:]]}).json()
        text = out["packet"]["text"]
        trace = client.get(f"/v1/trace/{out['trace_id']}").json()
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            again = audit.replay(conn, UUID(out["trace_id"]), RecallOptions(), policy=None)
        conv = conv_id(client, chat)
        pages = [client.get(u) for u in (f"/v1/inspector/c/{conv}", f"/v1/views/c/{conv}/working",
                                         f"/inspector/c/{conv}")]
    assert trace["policy"] == "packet-v20"
    assert f'<Fact kind="told" turn="8">세라 told 카이토: {PLAIN_TOLD}; about: 유나</Fact>' in text
    assert f"세라 told 카이토: {SECRET_VALUE}" not in text  # 하나 is in the scene: the secret it repeats keeps it out
    gated = [e for e in trace["lines"] if e.get("why") == "secret_gate" and e["kind"] == "fact"]
    assert len(gated) == 1 and gated[0]["label"] == "hidden" and gated[0]["text"] == ""
    assert again["status"] == "ok" and again["reproduced"] is True and again["text"] == text
    assert all(p.status_code == 200 for p in pages)
