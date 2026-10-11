"""PHASE-43 S4: the status told as core values and changes, placed even when its bar's message is in context."""

from __future__ import annotations

import json
from uuid import UUID

import psycopg
import pytest
from psycopg.rows import dict_row

from conftest import make_client
from nmos_sidecar import audit, statechange
from nmos_sidecar.retrieval import RecallOptions
from simchat import SimChat
from test_sidecar_integration import recall, sync

RULE = {"card": "Status test", "id": "bar", "kind": "block", "role": "char", "start": r"☆ \[", "end": r"\]\s*$", "separator": "|"}


def bar(day: int, hp: int, items: str = "물약 ×2 / 열쇠 / 지도", place: str = "광장") -> str:
    return f"길을 걷는다.\n☆ [Date: 1214년 9월 {day}일 | HP: {hp} / 200 | Place: {place} | Items: {items}]"


@pytest.fixture
def rules(tmp_path):
    path = tmp_path / "rules.json"
    path.write_text(json.dumps({"rules": [RULE]}), encoding="utf-8")
    return str(path)


def test_change_forms():
    assert statechange.change("44", "43") == "−1"
    assert statechange.change("1,200", "1,350") == "+150"
    assert statechange.change("115 / 200", "200 / 200") == "+85"
    assert statechange.change("115 / 200", "115 / 220") == "+0, max +20"
    assert statechange.change("물약 ×2 / 열쇠 / 지도", "물약 ×1 / 지도 / 횃불") == "+횃불 · −열쇠 · 물약 ×1 (−1)"
    assert statechange.change("1214년 9월 3일", "1214년 9월 4일") is None  # a date is text: no arithmetic
    assert statechange.change("광장", "광장") is None and statechange.change(None, "광장") is None


def window(position: int, **values: str) -> dict:
    return {"position": position, "turn": position // 2, "host_logical_id": f"m{position}", "values": values}


def test_core_keys_are_pins_and_keys_that_change_in_half_the_windows():
    wins = [window(2 * n + 1, Date=f"9월 {n}일", HP=str(100 - (n % 2)), Mood="평온", Gold="10") for n in range(10)]
    assert statechange.core_keys(wins) == {"Date", "HP"}
    assert statechange.core_keys(wins, frozenset({"Mood"})) == {"Date", "HP", "Mood"}
    rare = [window(2 * n + 1, Date="9월 1일", Gold=str(10 if n < 9 else 12)) for n in range(10)]
    assert statechange.core_keys(rare) == {"Date"}  # a scene key is core however rarely it changes; Gold changed once
    assert statechange.scene_key("도윤.location") and statechange.scene_key("시간") and not statechange.scene_key("Gold")


def test_tell_leaves_unchanged_keys_out_and_a_list_as_its_change():
    wins = [window(2 * n + 1, Date=f"9월 {n}일", HP="100", Items="물약 ×2 / 열쇠 / 지도", Place="광장")
            for n in range(5)]
    wins.append(window(11, Date="9월 5일", HP="99", Items="물약 ×1 / 열쇠 / 지도", Place="광장"))
    told = {t.key: t for t in statechange.tell(wins)}
    assert set(told) == {"Date", "HP", "Items", "Place"}  # Place is a scene key: told although unchanged
    assert told["Date"].value == "9월 5일" and told["Date"].since_previous is None
    assert (told["HP"].value, told["HP"].since_previous) == ("99", "−1")
    assert (told["Items"].value, told["Items"].since_previous) == ("", "물약 ×1 (−1)")
    asked = {t.key: t for t in statechange.tell(wins, asked=frozenset({"Items"}))}
    assert asked["Items"].value == "물약 ×1 / 열쇠 / 지도"
    first = statechange.tell(wins[:1])
    assert {t.key for t in first} == {"Date", "HP", "Items", "Place"}  # nothing to compare: every key is new


def test_the_current_date_reaches_the_packet_when_its_bar_is_in_context(migrated, rules):
    """A4, the incident's shape: the prompt holds the last reply (its status bar stripped by the preset), so the
    in-context rule withheld the date; told as changes, it is placed."""
    chat = SimChat()
    for day, hp in ((3, 200), (3, 180), (4, 180), (4, 150)):
        chat.user("계속.")
        chat.reply(bar(day, hp))
    chat.user("오늘 날짜가 며칠이지?")
    held = [m["chatId"] for m in chat.messages[-4:]]
    with make_client(migrated, parsers_file=rules, packet_policy="packet-v18") as c:
        sync(c, chat, character_name="Status test")
        out = recall(c, chat, "오늘 날짜가 며칠이지?", in_context=held, budget=1200)
        text = out["packet"]["text"]
        assert '<Item key="Date" as_of_turn="3">1214년 9월 4일</Item>' in text
        assert '<Item key="HP" as_of_turn="3" since_previous="−30">150 / 200</Item>' in text
        assert '<Item key="Place" as_of_turn="3">광장</Item>' in text  # a scene key, unchanged
        assert 'key="Items"' not in text  # unchanged, not core
        trace = c.get(f"/v1/trace/{out['trace_id']}").json()
        assert trace["recall_options"]["state_changes"] is True
        assert c.get(f"/v1/trace/{out['trace_id']}/replay").json()["reproduced"] is True
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            conn.execute("UPDATE retrieval_trace SET recall_options = recall_options - 'state_changes' - 'state_pins'"
                         " WHERE id = %s", (out["trace_id"],))
            old = audit.replay(conn, UUID(out["trace_id"]), RecallOptions())
        assert "<Item " not in old["text"]  # a trace without the option replays as before: in context, withheld
    with make_client(migrated, parsers_file=rules, packet_policy="packet-v17") as c:
        assert "<Item " not in recall(c, chat, "오늘 날짜가 며칠이지?", in_context=held, budget=1200)["packet"]["text"]


def test_a_history_question_draws_its_line_once(migrated, rules):
    chat = SimChat()
    for day, hp in ((3, 200), (3, 180), (4, 180), (4, 150)):
        chat.user("계속.")
        chat.reply(bar(day, hp))
    chat.user("HP 언제 이렇게 줄었지?")
    with make_client(migrated, parsers_file=rules, packet_policy="packet-v18") as c:
        sync(c, chat, character_name="Status test")
        text = recall(c, chat, "HP 언제 이렇게 줄었지?", budget=1200)["packet"]["text"]
        assert text.count('key="HP"') == 1 and '<StateHistory key="HP">' in text
