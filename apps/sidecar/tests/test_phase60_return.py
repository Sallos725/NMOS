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
from nmos_sidecar import audit, packet, retrieval, scene
from nmos_sidecar.entities import resolve
from nmos_sidecar.packet import BACK_AFTER_NOTE, Line, compile_lines
from nmos_sidecar.retrieval import RecallOptions, return_marks
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
