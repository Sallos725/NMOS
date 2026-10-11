"""PHASE-43 S1/S2: status windows found by their shape, tracked per card on confirmation, pinned keys."""

from __future__ import annotations

import json

import psycopg
import pytest
from psycopg.rows import dict_row

from conftest import make_client
from nmos_sidecar import parsers, statusshape
from simchat import SimChat
from test_sidecar_integration import recall, sync

CARD = "Shape test"
BLOCK_RULE = {"card": CARD, "id": "bar", "kind": "block", "role": "char", "start": r"\[Status:", "end": r"\]\s*$",
              "separator": "|"}


def bar(day: int, hp: int, place: str = "광장 [북문] 앞", items: str = "물약 ×2 / 열쇠 / 지도") -> str:
    return f"길을 걷는다.\n[Status:date=1214년 9월 {day}일|hp={hp} / 200|place={place}|items=<b>{items}</b>]"


def fields(text: str) -> list[dict[str, str]]:
    return [dict(b.fields) for b in statusshape.blocks(text)]


def test_the_detector_reads_labels_nested_brackets_and_colon_fields():
    assert fields(bar(4, 150)) == [{"date": "1214년 9월 4일", "hp": "150 / 200", "place": "광장 [북문] 앞",
                                    "items": "<b>물약 ×2 / 열쇠 / 지도</b>"}]
    assert fields("☆ [Date: 2024-08-21 (Wed) | Time: Dawn | Location: 던전 [광산] 보스룸 | Level: 32]") == [
        {"Date": "2024-08-21 (Wed)", "Time": "Dawn", "Location": "던전 [광산] 보스룸", "Level": "32"}]
    assert fields("[ 🎮 | Date: 3월 2일 | Time: 밤 | Location: 집 | 혼잣말이 길어진다. ]") == [
        {"Date": "3월 2일", "Time": "밤", "Location": "집"}]


@pytest.mark.parametrize("text", [
    "그는 말했다. \"a=b 이고 c=d 라니까.\" | 그리고 웃었다.",
    "| 이름 | 나이 | 직업 |\n|---|---|---|\n| 하나 | 17 | 학생 |",
    "[💡Request Profile| None ]",
    "[LBDATA START]\nauthor=하나|time=얼마 전|content=소문\n[LBDATA END]",
    "[[위키 링크]] 와 [링크](https://example.invalid) 그리고 [주의: 한 줄 | 메모]",
    "[INFO] a=1 | b=2 | c=3",
    "[그는 생각했다: 오늘은 | 이상하게도 | 길다. 정말로.]",
])
def test_text_that_is_not_a_status_window_proposes_none(text):
    assert statusshape.blocks(text) == []


def test_a_shape_rule_reads_what_the_block_rule_reads():
    block = parsers.compile_rules({"rules": [BLOCK_RULE]})
    shape = parsers.compile_rules({"rules": [{"card": CARD, "id": "s", "kind": "shape",
                                              "keys": ["date", "hp", "place", "items"]}]})
    for day in (3, 4):
        text = bar(day, 140 + day)
        assert ({k: v for _, k, v in parsers.parse(shape, text, "char", None, CARD)}
                == {k: v for _, k, v in parsers.parse(block, text, "char", None, CARD)})
    assert parsers.parse(shape, bar(4, 150), "char", None, "Other card") == []
    assert parsers.compile_rules({"rules": [{"card": CARD, "kind": "shape", "keys": ["a", "b"]}]}).errors


def story(days=((3, 200), (3, 180), (4, 180), (4, 150))) -> SimChat:
    chat = SimChat()
    for day, hp in days:
        chat.user("계속.")
        chat.reply(bar(day, hp))
    chat.user("다음.")
    return chat


def conversation(url: str, chat: SimChat):
    with psycopg.connect(url, row_factory=dict_row) as conn:
        return conn.execute("SELECT id FROM conversation WHERE host_chat_ref = %s", (chat.id,)).fetchone()["id"]


def config_rows(url: str):
    with psycopg.connect(url, row_factory=dict_row) as conn:
        return conn.execute("SELECT key, value FROM app_config ORDER BY key").fetchall()


def test_track_untrack_and_pins(migrated, tmp_path):
    other = {"card": CARD, "id": "mood", "kind": "regex", "role": "char", "pattern": r"기분: (?P<value>\S+)", "key": "mood"}
    path = tmp_path / "rules.json"
    path.write_text(json.dumps({"rules": [other]}), encoding="utf-8")
    chat = story()
    with make_client(migrated, parsers_file=str(path), packet_policy="packet-v18") as c:
        sync(c, chat, character_name=CARD)
        conv = conversation(migrated, chat)
        before = config_rows(migrated)
        found = c.get(f"/v1/conversations/{conv}/status/candidates").json()
        assert config_rows(migrated) == before  # looking never configures (Q1)
        assert found["card"] == CARD and found["pins"] == []
        [cand] = found["candidates"]
        assert cand["keys"] == ["date", "hp", "place", "items"] and cand["count"] == 4 and not cand["tracked"]
        assert "<State>" not in recall(c, chat, "다음.", budget=1200)["packet"]["text"]

        view = c.post("/v1/parsers/card/track", json={"card": CARD, "keys": cand["keys"]}).json()
        assert view["parsers"]["active_rules"] == 2  # the card's other rule stays (Q5)
        again = c.post("/v1/parsers/card/track", json={"card": CARD, "keys": cand["keys"]}).json()
        assert again["parsers"]["active_rules"] == 2  # the same key set twice: one rule
        [cand] = c.get(f"/v1/conversations/{conv}/status/candidates").json()["candidates"]
        assert cand["tracked"] and cand["rule_id"]
        text = recall(c, chat, "다음.", budget=1200)["packet"]["text"]
        assert '<Item key="date" as_of_turn="3">1214년 9월 4일</Item>' in text
        assert 'key="items"' not in text  # unchanged and not core

        assert c.put("/v1/parsers/card/pins", json={"card": CARD, "keys": ["items"]}).json()["pins"] == ["items"]
        out = recall(c, chat, "다음.", budget=1200)
        assert '<Item key="items" as_of_turn="3">물약 ×2 / 열쇠 / 지도</Item>' in out["packet"]["text"]
        trace = c.get(f"/v1/trace/{out['trace_id']}").json()
        assert trace["recall_options"]["state_pins"] == ["items"]
        assert c.get(f"/v1/trace/{out['trace_id']}/replay").json()["reproduced"] is True
        assert c.put("/v1/parsers/card/pins", json={"card": "", "keys": []}).status_code == 422

        # A new chat of the card with the same window is tracked without asking again (Q2).
        second = story(((7, 90), (8, 80), (8, 70)))
        sync(c, second, character_name=CARD)
        assert "1214년 9월 8일" in recall(c, second, "다음.", budget=1200)["packet"]["text"]

        view = c.post("/v1/parsers/card/untrack", json={"card": CARD, "rule_id": cand["rule_id"]}).json()
        assert view["parsers"]["active_rules"] == 1
        assert '"mood"' in json.dumps(c.get("/v1/config").json()["parsers"]["rules"])
        assert "<State>" not in recall(c, chat, "다음.", budget=1200)["packet"]["text"]
