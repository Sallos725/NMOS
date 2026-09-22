"""Phase 1: deterministic state parsers, current state through head membership, packet <State>."""

from __future__ import annotations

import json

import psycopg
import pytest
from psycopg.rows import dict_row

from conftest import make_client
from nmos_sidecar.parsers import compile_rules, parse
from nmos_sidecar.state import rebuild_state
from simchat import SimChat
from test_sidecar_integration import recall, sync

RULES = {
    "rules": [
        {"id": "status", "kind": "block", "start": r"```status", "end": r"```", "role": "char"},
        {"id": "hp", "kind": "regex", "pattern": r"❤️\s*(?P<value>\d+/\d+)", "key": "HP"},
        {"id": "broken", "kind": "regex", "pattern": r"(unclosed"},
    ]
}

STATUS = "The rain keeps falling.\n```status\n장소: 폐허가 된 성당\n시간｜새벽 3시\n- 기분: 불안\n```\n❤️ 42/100"


def test_parser_rules_block_and_regex():
    ruleset = compile_rules(RULES)
    assert len(ruleset.rules) == 2 and ruleset.errors and "broken" in ruleset.errors[0]
    pairs = {k: v for _, k, v in parse(ruleset, STATUS, "char", None)}
    assert pairs == {"장소": "폐허가 된 성당", "시간": "새벽 3시", "기분": "불안", "HP": "42/100"}
    assert parse(ruleset, STATUS, "user", None) == [("hp", "HP", "42/100")]  # block rule is char-only


@pytest.fixture
def state_client(migrated, tmp_path):
    rules = tmp_path / "rules.json"
    rules.write_text(json.dumps(RULES), encoding="utf-8")
    with make_client(migrated, parsers_file=str(rules)) as c:
        yield c


def fill(chat: SimChat, n: int) -> None:
    for i in range(n):
        chat.user(f"Small talk {i} about nothing in particular.")
        chat.reply(f"Reply {i} with nothing notable.")


def packet(client, chat, query="어디에 있지?", tail=6):
    in_context = [m["chatId"] for m in chat.messages[len(chat.messages) - tail:]] if tail else []
    return recall(client, chat, query, in_context=in_context)["packet"]["text"]


def test_state_follows_membership_and_is_injected_out_of_context(state_client, migrated):
    chat = SimChat()
    chat.user("Let us begin.")
    chat.reply(STATUS)
    fill(chat, 6)
    sync(state_client, chat)
    text = packet(state_client, chat)
    assert '<Item key="장소" as_of_turn="1">폐허가 된 성당</Item>' in text
    assert '<Item key="HP" as_of_turn="1">42/100</Item>' in text

    # A later status window supersedes the earlier one.
    chat.reply(STATUS.replace("폐허가 된 성당", "지하 묘지").replace("42/100", "30/100"))
    chat.user("next")
    sync(state_client, chat)
    later = packet(state_client, chat, tail=0)
    assert "지하 묘지" in later and "폐허가 된 성당" not in later

    # Deleting it brings the earlier value back (synchronous invalidation, D8).
    chat.delete(len(chat.messages) - 2)
    sync(state_client, chat)
    assert "폐허가 된 성당" in packet(state_client, chat, tail=0)

    # Editing the source message changes the state; the old value never returns.
    chat.edit(1, STATUS.replace("폐허가 된 성당", "종탑"))
    sync(state_client, chat)
    edited = packet(state_client, chat, tail=0)
    assert "종탑" in edited and "폐허가 된 성당" not in edited

    # In-context state is not repeated.
    assert "<State>" not in packet(state_client, chat, tail=len(chat.messages))

    # 'Cut Messages for AI' hides it.
    chat.disable(2, "allBefore")
    sync(state_client, chat)
    assert "<State>" not in packet(state_client, chat, tail=0)

    # Rebuildable.
    with psycopg.connect(migrated, row_factory=dict_row) as conn:
        before = conn.execute("SELECT source_revision_id, key, value FROM state_observation ORDER BY 1, 2").fetchall()
        rebuild_state(conn, compile_rules(RULES))
        after = conn.execute("SELECT source_revision_id, key, value FROM state_observation ORDER BY 1, 2").fetchall()
    assert before == after and before


def test_provisional_tail_state_waits_for_acceptance(state_client):
    chat = SimChat()
    chat.user("start")
    chat.reply(STATUS)
    sync(state_client, chat)
    assert "<State>" not in packet(state_client, chat, tail=0)  # reply not yet accepted (D5)
    chat.user("continue")
    sync(state_client, chat)
    assert "<State>" in packet(state_client, chat, tail=0)


def test_state_respects_budget(state_client):
    chat = SimChat()
    chat.user("start")
    chat.reply(STATUS)
    chat.user("go")
    sync(state_client, chat)
    out = recall(state_client, chat, "x", budget=70)["packet"]
    assert out["token_estimate"] <= 70


def test_inspector_and_read_apis(state_client):
    chat = SimChat(chat_id="<script>alert(1)</script>")
    chat.user("<b>hello</b> & bye")
    chat.reply(STATUS)
    chat.user("next")
    sync(state_client, chat)
    recall(state_client, chat, "hello")
    convs = state_client.get("/v1/conversations").json()
    conv_id = convs[0]["id"]
    assert state_client.get(f"/v1/conversations/{conv_id}/state").json()[0]["key"]
    assert state_client.get(f"/v1/conversations/{conv_id}/traces").json()
    index = state_client.get("/inspector")
    assert index.status_code == 200 and "<script>alert(1)" not in index.text and "&lt;script&gt;" in index.text
    detail = state_client.get(f"/inspector/c/{conv_id}").text
    assert "폐허가 된 성당" in detail and "&lt;b&gt;hello&lt;/b&gt; &amp; bye" in detail and "<b>hello" not in detail
    del state_client.headers["Authorization"]
    assert state_client.get("/inspector").status_code == 401
    assert state_client.get("/inspector", params={"token": "test-token"}).status_code == 200


def test_clean_text_keeps_visible_text_only():
    from nmos_sidecar.packet import clean_text
    raw = ('<style>.hp{color:red}</style><div class="status"><span>HP</span>: 30<br>장소: 성당</div>\n\n\n'
           '<script>x()</script>"안녕," 하나가 말했다. &amp; 끝')
    assert clean_text(raw) == 'HP: 30\n장소: 성당\n"안녕," 하나가 말했다. & 끝'


def test_sim_bot_state_is_scoped_per_character():
    ruleset = compile_rules({"rules": [
        {"id": "roster", "kind": "block", "start": r"<status>", "end": r"</status>",
         "entity_line": r"[\[【■]\s*(?P<entity>[^\]】]+?)\s*[\]】]?"},
        {"id": "inline", "kind": "regex", "pattern": r"(?P<entity>\S+)의 호감도\s*[:：]\s*(?P<value>\d+)", "key": "호감도"},
    ]})
    content = ("오늘의 교실.\n<status>\n[하나]\nHP: 30/100\n기분: 불안\n[카이토]\nHP: 80/100\n기분: 평온\n</status>\n"
               "하나의 호감도: 42 / 카이토의 호감도: 17")
    pairs = {k: v for _, k, v in parse(ruleset, content, "char", None)}
    assert pairs == {"하나.HP": "30/100", "하나.기분": "불안", "카이토.HP": "80/100", "카이토.기분": "평온",
                     "하나.호감도": "42", "카이토.호감도": "17"}
