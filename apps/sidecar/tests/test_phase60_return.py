"""PHASE-60 S4 (A10, A12; ADR 0082 items 4, 5, 7): back after a long absence, and what just ended, under packet-v20.

The rules themselves are `absence.py` (tests/test_phase60_absence.py); these tests cover which rows feed them, where
the mark and the lines go, the Note, resting, the memory modes and the echo rule. Synthetic names only.
"""

from __future__ import annotations

import uuid
from uuid import UUID

import psycopg
import pytest
from psycopg.rows import dict_row

from conftest import make_client
from memeval import stub_extractor
from nmos_sidecar import audit, overuse, packet, retrieval, scene, threads
from nmos_sidecar.entities import resolve
from nmos_sidecar.facts import settled_entry, thread_entry
from nmos_sidecar.packet import BACK_AFTER_NOTE, SETTLED_NOTE, Line, compile_lines
from nmos_sidecar.retrieval import Gathered, RecallOptions, return_marks, settled_lines
from simchat import SimChat
from test_extraction import drain
from test_generations import LLM
from test_semantics import row
from test_sidecar_integration import recall, sync

C = {"subject_type": "character"}
ALL = frozenset(range(0, 500))


def seen(turn: int, who: str, **kw) -> dict:
    """An ordinary narrated row about `who` at `turn`."""
    return row(turn, who, "event", None, f"walks in {turn}", **C, **kw)


def plain(i: int, who: str = "세라") -> Line:
    return Line("fact", f'    <Fact kind="located_in" turn="{i}">{who} located in: 정원</Fact>', {"assertion": f"c{i}"},
                i, f"{who} located in: 정원", "정원")


def marks_of(rows, now: int, served=ALL, names=("세라",), persona=(), assertions: bool = True) -> dict[str, str]:
    r = resolve(uuid.uuid4(), rows, persona=persona)
    cast = {scene.key(r, n): n for n in names}
    view = {"facts": list(rows), "claims": [], "other": [], "threads": [], "excluded": {}}
    if assertions:
        view["assertions"] = list(rows)
    return return_marks(view, r, cast, [(n, [plain(now - 1, n)]) for n in names], now, served)


# --- the return gap (pure) --------------------------------------------------------------------------------------------


def test_marked_at_40_served_turns_and_not_at_39():
    # appearances 10 and 51: turns 11..50 between them, 40 served
    assert marks_of([seen(10, "세라"), seen(51, "세라")], now=52) == {"세라": "~40 turns"}
    # appearances 10 and 50: 39 between them
    assert marks_of([seen(10, "세라"), seen(50, "세라")], now=52) == {}


def test_unserved_turns_in_the_gap_are_not_counted():
    rows = [seen(10, "세라"), seen(56, "세라")]  # 45 turns between them
    assert marks_of(rows, now=57) == {"세라": "~50 turns"}
    unserved = frozenset(range(20, 30))  # 10 nobody extracted: 35 counted, no mark
    assert marks_of(rows, now=57, served=ALL - unserved) == {}
    assert marks_of(rows, now=57, served=lambda t: t not in unserved) == {}


def test_not_for_a_first_appearance():
    assert marks_of([seen(50, "세라"), seen(52, "세라")], now=53) == {}
    assert marks_of([seen(10, "카이토"), seen(52, "세라")], now=53) == {}


def test_not_when_the_run_began_six_turns_ago():
    assert marks_of([seen(10, "세라"), seen(46, "세라"), seen(50, "세라")], now=52) == {}  # began at 46 = 52 - 6
    assert marks_of([seen(10, "세라"), seen(55, "세라"), seen(59, "세라")], now=60) == {"세라": "~40 turns"}  # 55 = 60 - 5


def test_not_for_the_persona():
    rows = [seen(10, "{{user}}"), seen(60, "{{user}}")]
    assert marks_of(rows, now=61, names=("{{user}}",)) == {}
    rows = [seen(10, "타쿠미"), seen(60, "타쿠미")]
    assert marks_of(rows, now=61, names=("타쿠미",), persona=["타쿠미"]) == {}


def test_rounded_to_ten_halves_up():
    assert marks_of([seen(10, "세라"), seen(51, "세라")], now=52) == {"세라": "~40 turns"}
    assert marks_of([seen(10, "세라"), seen(56, "세라")], now=57) == {"세라": "~50 turns"}
    assert marks_of([seen(10, "세라"), seen(55, "세라")], now=56) == {"세라": "~40 turns"}  # 44


def test_object_and_participant_rows_are_appearances():
    obj = row(10, "카이토", "feels_toward", "세라", "그리움", **C, object_type="character")
    assert marks_of([obj, seen(51, "세라")], now=52) == {"세라": "~40 turns"}
    part = seen(10, "카이토", participants=[{"name": "세라", "type": "character"}])
    assert marks_of([part, seen(51, "세라")], now=52) == {"세라": "~40 turns"}
    # an appearance in between (as object) ends the absence
    mid = row(30, "카이토", "feels_toward", "세라", "그리움", **C, object_type="character")
    assert marks_of([seen(10, "세라"), mid, seen(51, "세라")], now=52) == {}


def test_a_superseded_row_still_counts_as_an_appearance():
    """The view's facts hold the current version only: the appearances come from every assertion."""
    rows = [seen(10, "세라"), row(30, "세라", "located_in", "정원", None, **C, object_type="place"),
            row(60, "세라", "located_in", "항구", None, **C, object_type="place")]
    current = [rows[0], rows[2]]  # turn 30's place was replaced at turn 60
    r = resolve(uuid.uuid4(), rows)
    cast = {scene.key(r, "세라"): "세라"}
    view = {"facts": current, "claims": [], "other": [], "threads": [], "excluded": {}, "assertions": rows}
    assert return_marks(view, r, cast, [("세라", [plain(59)])], 61, ALL) == {}  # 29 since turn 30
    view.pop("assertions")
    assert return_marks(view, r, cast, [("세라", [plain(59)])], 61, ALL) == {"세라": "~50 turns"}  # without it: 49


def test_canon_and_carried_rows_are_not_appearances():
    canon = seen(-1, "세라", canon=True)
    assert marks_of([canon, seen(10, "세라"), seen(51, "세라")], now=52) == {"세라": "~40 turns"}
    assert marks_of([canon, seen(51, "세라")], now=52) == {}  # canon is no earlier appearance
    # carry hook: a row carried from another chat is no appearance
    assert marks_of([seen(10, "세라", carried=True), seen(51, "세라")], now=52) == {}
    assert marks_of([seen(10, "세라"), seen(30, "세라", carried=True), seen(51, "세라")], now=52) == {
        "세라": "~40 turns"}


def test_only_characters_with_a_cast_group():
    rows = [seen(10, "세라"), seen(51, "세라")]
    r = resolve(uuid.uuid4(), rows)
    cast = {scene.key(r, "세라"): "세라"}
    view = {"facts": rows, "claims": [], "other": [], "threads": [], "excluded": {}, "assertions": rows}
    assert return_marks(view, r, cast, [], 52, ALL) == {}


def test_served_is_read_only_when_a_gap_is_possible():
    asked: list[int] = []

    def served(t: int) -> bool:
        asked.append(t)
        return True

    assert marks_of([seen(30, "세라"), seen(51, "세라")], now=52, served=served) == {}
    assert asked == []  # 20 turns at most: no need to know which were served
    assert marks_of([seen(10, "세라"), seen(51, "세라")], now=52, served=served) == {"세라": "~40 turns"}
    assert asked


def test_older_policies_mark_nothing():
    rows = [seen(10, "세라"), seen(51, "세라")]
    r = resolve(uuid.uuid4(), rows)
    cast = {scene.key(r, "세라"): "세라"}
    view = {"facts": rows, "claims": [], "other": [], "threads": [], "excluded": {}, "assertions": rows}
    for policy in ("packet-v19", "packet-v8"):
        assert retrieval.return_marks(view, r, cast, [("세라", [plain(51)])], 52, ALL, policy=policy) == {}


# --- the mark on the tag -----------------------------------------------------------------------------------------------


def test_the_character_tag_carries_the_mark_with_its_note():
    cast = [("세라", [plain(51)]), ("카이토", [plain(50, "카이토")])]
    out = compile_lines([], 2000, cast=cast, cast_marks={"세라": "~40 turns"}, policy="packet-v20")
    assert '    <Character name="세라" back_after="~40 turns">\n      <Fact kind="located_in"' in out.text
    assert '    <Character name="카이토">\n' in out.text
    assert out.text.count("back_after") == 2 and BACK_AFTER_NOTE in out.text  # the tag, and the Note's sentence
    plain_out = compile_lines([], 2000, cast=cast, policy="packet-v20")
    assert "back_after" not in plain_out.text and BACK_AFTER_NOTE not in plain_out.text
    # the longer opening and the Note are part of the first line's cost
    first = lambda o: next(e for e in o.ledger if e["ref"] == {"assertion": "c51"})  # noqa: E731
    assert first(out)["tok"] > first(plain_out)["tok"]
    assert first(out)["label"] == "required"


def test_older_policies_ignore_the_mark_byte_for_byte():
    cast = [("세라", [plain(51)])]
    for policy in ("packet-v19", "packet-v14", "packet-v8"):
        marked = compile_lines([], 2000, cast=cast, cast_marks={"세라": "~40 turns"}, policy=policy)
        bare = compile_lines([], 2000, cast=cast, policy=policy)
        assert marked.text == bare.text and marked.ledger == bare.ledger
    # the Note's sentence never fires under an older policy, even for a value that spells the mark
    odd = Line("fact", '    <Fact kind="has_trait" turn="4">하나 has trait: back_after="x"</Fact>', {"assertion": "o"},
               4, "x", "x")
    assert BACK_AFTER_NOTE not in compile_lines([], 2000, facts=[odd], policy="packet-v19").text


def test_an_echoed_character_tag_leaves_no_trace_of_the_mark():
    """A12 / ADR 0082 item 7: the mark is an attribute of <Character>, a bare tag the normalizer strips."""
    cleaned = packet.clean_text('카이토가 웃었다. <Character name="세라" back_after="~40 turns"> 바람이 분다.')
    assert "back_after" not in cleaned and "~40" not in cleaned and "Character" not in cleaned
    assert cleaned == "카이토가 웃었다. 바람이 분다."


# --- end to end (stub model, test database) --------------------------------------------------------------------------


def long_absence(c, url: str) -> SimChat:
    chat = SimChat()
    chat.user("세라 is in the garden.")
    chat.reply("Noted.")
    for i in range(1, 50):
        chat.user(f"Idle chatter {i} about clouds.")
        chat.reply("Noted.")
    chat.user("세라 moved to the harbor.")  # turn 50: back; turn 0's place was replaced
    chat.reply("Noted.")
    chat.user("오늘은 날씨가 맑네.")  # turn 51: the request
    sync(c, chat)
    drain(url, stub_extractor)
    return chat


@pytest.mark.parametrize("policy", ["packet-v20", "packet-v19"])
def test_a_returning_character_is_marked_under_v20_only_and_replays(migrated, policy):
    with make_client(migrated, packet_policy=policy, **LLM) as c:
        chat = long_absence(c, migrated)
        out = recall(c, chat, "오늘은 날씨가 맑네.", in_context=[m["chatId"] for m in chat.messages[-4:]], budget=1500)
        text = out["packet"]["text"]
    assert '<Character name="세라"' in text
    if policy == "packet-v20":
        assert '<Character name="세라" back_after="~50 turns">' in text and BACK_AFTER_NOTE in text
        with psycopg.connect(migrated, row_factory=dict_row) as conn:  # served turns are read as of the request (D39)
            again = audit.replay(conn, UUID(out["trace_id"]), RecallOptions(), policy=None)
            as_v19 = audit.replay(conn, UUID(out["trace_id"]), RecallOptions(), policy="packet-v19")
        assert again["status"] == "ok" and again["reproduced"] is True and again["text"] == text
        assert "back_after" not in as_v19["text"]
    else:
        assert "back_after" not in text and BACK_AFTER_NOTE not in text


# --- settled lines -------------------------------------------------------------------------------------------------------


PROMISE_NOTE = dict(packet.NOTE_EXTRAS)['<Thread kind="promise"']
V20 = RecallOptions(policy="packet-v20")


def closed(tid: int, status: str, closed_turn: int | None, by: str = "세라", to: str | None = "카이토",
           text: str | None = None, **kw) -> dict:
    """A thread as `threads.fold` leaves it, opened at turn `tid` and closed at `closed_turn`."""
    kind = "promise" if status in ("open", "kept", "broken") else "goal"
    return {"id": tid, "kind": kind, "by": by, "to": to, "text": text or f"약속 {tid}", "turn": tid, "position": tid,
            "host_logical_id": f"m{tid}", "names": [by, *([to] if to else [])], "status": status,
            "closed_by": None if closed_turn is None else {"id": 1000 + tid, "turn": closed_turn,
                                                         "position": closed_turn},
            "restated": [], **kw}


def scene_of(items: list[dict], present=("세라", "카이토"), query: str = "", now: int = 50,
             persona=()) -> tuple[Gathered, dict, object]:
    rows = [seen(now - 1, n) for n in present]
    r = resolve(uuid.uuid4(), rows, persona=persona)
    g = Gathered()
    g.cast = scene.cast(rows, r, query, "", now)
    view = {"facts": rows, "claims": [], "other": [], "threads": items, "excluded": {}}
    return g, view, r


def settled_of(items, present=("세라", "카이토"), query: str = "", now: int = 50, rest=frozenset(),
               options: RecallOptions = V20, persona=()) -> tuple[list[Line], Gathered]:
    g, view, r = scene_of(items, present, query, now, persona)
    return settled_lines(g, view, r, query, now, rest, options), g


def ids(lines: list[Line]) -> list[int]:
    return [line.ref["assertion"] for line in lines]


def test_the_line_shape():
    t = closed(10, "broken", 20)
    line = settled_entry(t)
    assert line.xml == ('    <Thread status="broken" kind="promise" by="세라" to="카이토" turn="10" closed_turn="20">'
                        '약속 10</Thread>')
    assert line.kind == "thread" and line.ref == {"assertion": 10} and line.marks == {"settled": "broken"}
    assert line.text == "세라 → 카이토 (broken): 약속 10" and line.content == "약속 10"
    goal = settled_entry(closed(11, "achieved", 21, to=None))
    assert goal.xml == '    <Thread status="achieved" kind="goal" by="세라" turn="11" closed_turn="21">약속 11</Thread>'


def test_at_most_three_broken_before_kept_then_newest():
    items = [closed(1, "kept", 49), closed(2, "broken", 40), closed(3, "achieved", 50), closed(4, "failed", 46),
             closed(5, "open", None)]
    lines, _ = settled_of(items)
    assert ids(lines) == [4, 2, 3]


def test_only_inside_fifteen_turns():
    lines, _ = settled_of([closed(1, "broken", 34), closed(2, "kept", 35)])
    assert ids(lines) == [2]  # 16 turns ago: none; 15: kept


def test_maker_or_recipient_in_the_scene_or_named():
    items = [closed(1, "kept", 45, by="세라", to="하나"), closed(2, "kept", 46, by="하나", to="카이토"),
             closed(3, "kept", 47, by="하나", to="유나")]
    assert ids(settled_of(items)[0]) == [2, 1]  # 3: neither in the scene
    assert ids(settled_of(items, present=("세라",))[0]) == [1]
    assert ids(settled_of(items, present=("세라",), query="유나는 어떻게 됐어?")[0]) == [3, 1]  # named


def test_the_persona_does_not_make_a_thread_involved():
    items = [closed(1, "kept", 45, by="{{user}}", to="하나"), closed(2, "kept", 46, by="하나", to="{{user}}")]
    assert settled_of(items, present=("세라",))[0] == []
    items = [closed(3, "kept", 46, by="하나", to="타쿠미")]
    assert settled_of(items, present=("세라", "타쿠미"), persona=["타쿠미"])[0] == []


def test_a_carried_thread_has_no_settled_line():
    """Carry hook: settled lines come only from the chat's own threads."""
    assert settled_of([closed(1, "broken", 45, carried=True)])[0] == []
    assert ids(settled_of([closed(1, "broken", 45, carried=True), closed(2, "kept", 44)])[0]) == [2]


def test_older_policies_and_no_turn_give_none():
    items = [closed(1, "broken", 45)]
    for policy in ("packet-v19", "packet-v14"):
        assert settled_of(items, options=RecallOptions(policy=policy))[0] == []
    g, view, r = scene_of(items)
    assert settled_lines(g, view, r, "", None, frozenset(), V20) == []


def open_line(tid: int) -> Line:
    return thread_entry(closed(tid, "open", None))


def test_placed_after_the_open_threads_outside_their_limit_supportive():
    lines, _ = settled_of([closed(1, "kept", 45), closed(2, "broken", 40), closed(3, "achieved", 48)])
    opened = [open_line(30), open_line(31), open_line(32)]
    out = compile_lines([], 3000, threads=opened, settled=lines, policy="packet-v20")
    body = out.text.split("<Threads>\n", 1)[1].split("  </Threads>", 1)[0].splitlines()
    assert [b.split(">", 1)[0] for b in body] == [
        '    <Thread kind="promise" by="세라" to="카이토" turn="30"',
        '    <Thread kind="promise" by="세라" to="카이토" turn="31"',
        '    <Thread kind="promise" by="세라" to="카이토" turn="32"',
        '    <Thread status="broken" kind="promise" by="세라" to="카이토" turn="2" closed_turn="40"',
        '    <Thread status="achieved" kind="goal" by="세라" to="카이토" turn="3" closed_turn="48"',
        '    <Thread status="kept" kind="promise" by="세라" to="카이토" turn="1" closed_turn="45"']
    entries = [e for e in out.ledger if (e.get("marks") or {}).get("settled")]
    assert len(entries) == 3 and all(e["placed"] and e["kind"] == "thread" for e in entries)
    assert {e["label"] for e in entries} == {"supportive"}
    assert SETTLED_NOTE in out.text and PROMISE_NOTE in out.text  # open promises are placed too


def test_the_promise_note_is_not_said_for_a_settled_promise():
    lines, _ = settled_of([closed(1, "broken", 45)])
    out = compile_lines([], 2000, settled=lines, policy="packet-v20")
    assert '<Thread status="broken" kind="promise"' in out.text
    assert SETTLED_NOTE in out.text and PROMISE_NOTE not in out.text
    none = compile_lines([], 2000, threads=[open_line(30)], policy="packet-v20")
    assert SETTLED_NOTE not in none.text


def test_older_policies_ignore_settled_lines_byte_for_byte():
    lines, _ = settled_of([closed(1, "broken", 45)])
    for policy in ("packet-v19", "packet-v14", "packet-v8"):
        with_settled = compile_lines([], 2000, threads=[open_line(30)], settled=lines, policy=policy)
        without = compile_lines([], 2000, threads=[open_line(30)], policy=policy)
        assert with_settled.text == without.text and with_settled.ledger == without.ledger
    odd = Line("fact", '    <Fact kind="has_trait" turn="4">하나 has trait: <Thread status="x"</Fact>',
               {"assertion": "o"}, 4, "x", "x")
    assert SETTLED_NOTE not in compile_lines([], 2000, facts=[odd], policy="packet-v19").text


def test_a_settled_line_is_not_folded_into_the_reopened_promise():
    """`threads.fold` opens a similar promise afresh after a close: both lines are placed."""
    old = closed(10, "broken", 45, text="등대 앞에서 만나기")
    lines, _ = settled_of([old])
    again = thread_entry(closed(47, "open", None, text="등대 앞에서 만나기"))
    out = compile_lines([], 2000, threads=[again], settled=lines, policy="packet-v20")
    assert out.text.count("등대 앞에서 만나기") == 2
    assert all(e["placed"] for e in out.ledger if e["kind"] == "thread")


def test_a_settled_line_rests_like_a_supportive_line():
    lines, _ = settled_of([closed(1, "broken", 45)])
    ledger = compile_lines([], 2000, settled=lines, policy="packet-v20").ledger
    quiet = overuse.of_ledger(ledger, "날씨 이야기만 했다.", ("", ""))
    rest = overuse.tired([quiet, quiet], 2)
    assert ("thread", "1") in rest
    awake, g = settled_of([closed(1, "broken", 45), closed(2, "kept", 44)], rest=rest)
    assert ids(awake) == [2] and g.rested == 1
    # a tired line does not hold one of the three places
    many = [closed(1, "broken", 45), closed(2, "failed", 44), closed(3, "kept", 43), closed(4, "kept", 42)]
    assert ids(settled_of(many, rest=rest)[0]) == [2, 3, 4]
    # a reply that used it: not tired
    used = overuse.of_ledger(ledger, "그는 약속 1을 어겼다.", ("", ""))
    assert ("thread", "1") not in overuse.tired([used, quiet], 2)


def test_a_settled_line_shares_its_rest_key_with_the_open_line():
    """Deliberate: one thread is one line across requests (`overuse.key`: kind and assertion). An open line placed
    unused in the last two requests rests after its thread closes, as it would have rested open."""
    ledger = compile_lines([], 2000, threads=[open_line(1)], policy="packet-v20").ledger
    quiet = overuse.of_ledger(ledger, "날씨 이야기만 했다.", ("", ""))
    rest = overuse.tired([quiet, quiet], 2)
    assert settled_of([closed(1, "broken", 45)], rest=rest)[0] == []


SECRET = {"knowledge": "limited", "known_by": ["세라", "{{user}}"], "hidden_from": ["카이토"]}


def test_a_private_settled_line_follows_the_scene():
    lines, g = settled_of([closed(1, "broken", 45, **SECRET)])
    assert len(lines) == 1 and lines[0].private
    out = compile_lines([], 2000, settled=lines, policy="packet-v20")
    private = out.text.split("<Private>", 1)[1].split("</Private>", 1)[0]
    assert ('<Thread status="broken" kind="promise" by="세라" to="카이토" turn="1" closed_turn="45" '
            'known_by="세라, {{user}}" hidden_from="카이토">') in private
    assert "<Threads>" not in out.text and packet.PRIVATE_NOTE in out.text


def test_strict_and_narrator_modes_withhold_a_private_settled_line():
    lines, g = settled_of([closed(1, "broken", 45, **SECRET)], options=RecallOptions(policy="packet-v20", strict=True))
    assert [line.kind for line in lines] == ["secret"] and "약속 1" not in lines[0].xml and g.withheld == 1
    lines, g = settled_of([closed(1, "broken", 45, **SECRET)], options=RecallOptions(policy="packet-v20", narrator="카이토"))
    assert lines == [] and g.withheld == 1


def test_an_echoed_settled_line_is_dropped_by_the_normalizer():
    """A12 / ADR 0082 item 7: a settled line is a <Thread> with its content: clean-v3 drops the echo whole (K27)."""
    xml = settled_entry(closed(1, "broken", 45, text="등대 앞에서 만나기")).xml.strip()
    cleaned = packet.clean_text(f"카이토가 고개를 숙였다. {xml} 바람이 분다.")
    assert "등대" not in cleaned and "broken" not in cleaned and "status" not in cleaned
    assert cleaned == "카이토가 고개를 숙였다. 바람이 분다."


@pytest.mark.parametrize("policy", ["packet-v20", "packet-v19"])
def test_a_broken_promise_is_a_settled_line_under_v20_only_and_replays(migrated, policy):
    with make_client(migrated, packet_policy=policy, **LLM) as c:
        chat = SimChat()
        for line in ('세라 says to 카이토: "I promise to meet at the lighthouse."', "Idle chatter 1 about clouds.",
                     "Idle chatter 2 about clouds.", "세라 breaks the promise to 카이토 to meet at the lighthouse.",
                     "Idle chatter 3 about clouds.", "Idle chatter 4 about clouds."):
            chat.user(line)
            chat.reply("Noted.")
        chat.user("카이토, 세라 얘기 좀 해줘.")
        sync(c, chat)
        drain(migrated, stub_extractor)
        out = recall(c, chat, "카이토, 세라 얘기 좀 해줘.", in_context=[m["chatId"] for m in chat.messages[-4:]],
                     budget=1500)
        text = out["packet"]["text"]
    if policy == "packet-v20":
        assert ('<Thread status="broken" kind="promise" by="세라" to="카이토" turn="0" closed_turn="3">'
                'meet at the lighthouse</Thread>') in text
        assert SETTLED_NOTE in text and PROMISE_NOTE not in text
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            again = audit.replay(conn, UUID(out["trace_id"]), RecallOptions(), policy=None)
        assert again["status"] == "ok" and again["reproduced"] is True and again["text"] == text
        entry = next(e for e in again["lines"] if (e.get("marks") or {}).get("settled"))
        assert entry["placed"] and entry["label"] == "supportive" and entry["kind"] == "thread"
    else:
        assert "status=" not in text and SETTLED_NOTE not in text


def test_a_similar_promise_opens_afresh_thirty_turns_after_it_broke():
    """PHASE-60 S4: a restatement joins only an open thread; `threads.fold` is unchanged."""
    words = "등대 앞에서 만나기"
    base = {"subject_type": "character", "object_type": "character"}
    rows = [row(10, "세라", "promised", "카이토", words, **base),
            row(20, "세라", "promised", "카이토", words, polarity="negative", **base),
            row(50, "세라", "promised", "카이토", words, **base)]
    folded, unmatched, _ = threads.fold(rows, resolve(uuid.uuid4(), rows))
    assert unmatched == []
    assert [(t["id"], t["status"]) for t in folded] == [(50, "open"), (10, "broken")]
    assert folded[1]["closed_by"]["turn"] == 20
