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


@pytest.mark.parametrize("spec", [[], None, {}, {"rules": None}, {"rules": {}}, {"rules": [None]},
    {"rules": [{"kind": "regex", "pattern": None, "key": "HP"}]},
    {"rules": [{"kind": "block", "start": 7, "end": "END"}]},
    {"rules": [{"kind": "block", "start": "START", "end": None}]},
    {"rules": [{"kind": "block", "start": "START", "end": "END", "entity_line": []}]},
    {"rules": [{"kind": "regex", "pattern": "(?P<value>.+)", "key": 7}]}])
def test_malformed_parser_structure_is_reported_without_crashing(spec):
    ruleset = compile_rules(spec)
    assert ruleset.errors and not ruleset.rules


def test_parser_file_skips_malformed_rules_but_keeps_valid_ones(tmp_path, caplog):
    from nmos_sidecar.parsers import load_rules

    path = tmp_path / "rules.json"
    path.write_text(json.dumps({"rules": [None, {"kind": "regex", "pattern": None}, RULES["rules"][1]]}))
    ruleset = load_rules(str(path))
    assert len(ruleset.errors) == 2 and len(ruleset.rules) == 1
    assert parse(ruleset, STATUS, "char", None) == [("hp", "HP", "42/100")]
    assert "parser rule skipped" in caplog.text
    assert compile_rules({"rules": []}).errors == ()


def test_bad_parser_config_keeps_saved_rules_and_state(client, migrated):
    valid = {"rules": [RULES["rules"][1]]}
    assert client.put("/v1/config", json={"parsers": valid}).status_code == 200
    chat = SimChat()
    chat.user("Begin.")
    chat.reply(STATUS)
    chat.user("Next.")
    conv = sync(client, chat)["conversation_id"]
    before_config = client.get("/v1/config").json()["parsers"]
    before_state = client.get(f"/v1/conversations/{conv}/state").json()
    assert before_state
    with psycopg.connect(migrated, row_factory=dict_row) as conn:
        before_rows = conn.execute("SELECT * FROM state_observation ORDER BY source_revision_id, key").fetchall()
    for bad in [[], {"rules": None}, {"rules": [None]}, {"rules": [{"kind": "regex", "pattern": None}]}]:
        rejected = client.put("/v1/config", json={"parsers": bad})
        assert rejected.status_code == 422 and "parsers" in rejected.text
        assert client.get("/v1/config").json()["parsers"] == before_config
        assert client.get(f"/v1/conversations/{conv}/state").json() == before_state
    with psycopg.connect(migrated, row_factory=dict_row) as conn:
        assert conn.execute("SELECT * FROM state_observation ORDER BY source_revision_id, key").fetchall() == before_rows
    assert client.put("/v1/config", json={"parsers": {"rules": []}}).status_code == 200
    assert client.get(f"/v1/conversations/{conv}/state").json() == []


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
    # the reply at position 1 answers the first user message: turn 0 (packet-v7, ADR 0041)
    assert '<Item key="장소" as_of_turn="0">폐허가 된 성당</Item>' in text
    assert '<Item key="HP" as_of_turn="0">42/100</Item>' in text

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


def test_clean_text_drops_model_reasoning():
    from nmos_sidecar.packet import clean_text
    raw = "<Thoughts>\n우리가 도서관에 도착했을 때...\n</Thoughts>\n도서관 창가 자리, 하나는 노트를 펼쳤다.<think>hmm</think>"
    assert clean_text(raw) == "도서관 창가 자리, 하나는 노트를 펼쳤다."


def test_clean_text_drops_inline_images_and_media_tokens():
    # Image plugins insert <div><img src="data:…;base64,…"></div> or RisuAI inlay tokens into the
    # message itself; neither is story, and a base64 URI outgrows the old 500-char tag limit.
    from nmos_sidecar.packet import clean_text
    b64 = "iVBORw0KGgo" + "A" * 4000 + "=="
    raw = (f'하나는 창밖을 보았다.\n<div style="text-align:center">\n<img\n  src="data:image/png;base64,{b64}"\n'
           f'  alt="장면" style="max-width: 100%">\n</div>\n{{{{inlay::0b1c2d3e-aaaa-bbbb-cccc-1234567890ab}}}}'
           f'{{{{inlayeddata::f00d}}}} {{{{img::smile}}}} ![장면](data:image/webp;base64,{b64})\n'
           f'data:image/jpeg;base64,{b64}\n"가자." 카이토가 말했다.')
    assert clean_text(raw) == '하나는 창밖을 보았다.\n"가자." 카이토가 말했다.'


def test_clean_text_keeps_angle_brackets_that_are_not_tags():
    from nmos_sidecar.packet import clean_text
    assert clean_text("HP < 30 이면 도망친다. 3 > 2, <3 &quot;좋아&quot;") == 'HP < 30 이면 도망친다. 3 > 2, <3 "좋아"'


def test_clean_text_drops_illustration_plugin_markup():
    # Shape of a real illustration-plugin insert: the span's style outgrows 500 chars and the img src is a
    # {{raw::asset}} token. clean-v1 left the whole <img …> tag in the text.
    from nmos_sidecar.packet import clean_text
    mid, asset = "00000000-0000-4000-8000-000000000001", "Hana.__am__.chat.00000000-0000-4000-8000-000000000002"
    style = "display:flex;justify-content:center;margin:14px auto;width:var(--am-chat-image-width,70%);" * 8
    raw = (f'하나는 고개를 들었다.\n<div class="am-illustration-projection" data-am-message-id="{mid}" '
           f'data-am-slot-index="41" data-am-asset="{asset}"><span class="am-image" style="{style}">'
           f'<img class="am-image__media" data-am-asset="{asset}" src="{{{{raw::{asset}}}}}" width="1024" alt="" '
           f'loading="lazy" style="width:calc(760px * var(--am-chat-image-scale,1));max-width:100%"></span></div>\n'
           '"괜찮아." 하나가 말했다.')
    assert clean_text(raw) == '하나는 고개를 들었다.\n"괜찮아." 하나가 말했다.'


def test_clean_text_does_not_read_prose_as_a_tag():
    from nmos_sidecar.packet import clean_text
    assert clean_text("x<b 는 크다\n그리고 3 > 2") == "x<b 는 크다\n그리고 3 > 2"
    assert clean_text('<a href="x"\n  title=\'y\'>링크</a> <b>굵게</b><br/>끝') == "링크 굵게\n끝"


# --- PHASE-39 Q1, Q2: a one-line status bar, read field by field; a rule bound to one card --------------------------

BAR = ("The bell rang twice.\n[Notice: harbor | To: Hana]\n"
       "☆ [Date: 0003-05-17 (Sun) | Time: 06:20 | Level: 3 | HP: 40 / 50 | Items: 물약 ×2 / 해독제 ×1 | Gold: 1,200]\n")
EQUALS = "선실로 돌아왔다.\n[Status:date=0712-03-21|time=07:05|location=3번 선실|mood=느긋|wind=없음]"


def test_a_one_line_status_bar_is_read_field_by_field():
    ruleset = compile_rules({"rules": [
        {"id": "bar", "kind": "block", "role": "char", "start": r"☆ \[", "end": r"\]", "separator": "|"},
        {"id": "eq", "kind": "block", "role": "char", "start": r"\[Status:", "end": r"\]", "separator": "|"},
    ]})
    assert not ruleset.errors
    assert {k: v for _, k, v in parse(ruleset, BAR, "char", None)} == {
        "Date": "0003-05-17 (Sun)", "Time": "06:20", "Level": "3", "HP": "40 / 50", "Items": "물약 ×2 / 해독제 ×1",
        "Gold": "1,200"}  # the story's own bracket window ([Notice: … | To: …]) is not the bar
    assert {k: v for _, k, v in parse(ruleset, EQUALS, "char", None)} == {
        "date": "0712-03-21", "time": "07:05", "location": "3번 선실", "mood": "느긋", "wind": "없음"}
    # A bar longer than one value's limit still gives every field (each is cleaned on its own).
    long = "☆ [" + " | ".join(f"Skill{i}: {'x' * 40}" for i in range(30)) + "]"
    assert len(parse(ruleset, long, "char", None)) == 30


def test_a_rule_bound_to_a_card_reads_only_its_chats():
    ruleset = compile_rules({"rules": [
        {"id": "bar", "kind": "block", "start": r"☆ \[", "end": r"\]", "separator": "|", "card": "Card A"}]})
    assert parse(ruleset, BAR, "char", None, "Card A")
    assert parse(ruleset, BAR, "char", None, "Card B") == []
    assert parse(ruleset, BAR, "char", None) == []
    bad = compile_rules({"rules": [
        {"id": "s", "kind": "block", "start": "a", "end": "b", "separator": ""},
        {"id": "c", "kind": "block", "start": "a", "end": "b", "card": " "}]})
    assert not bad.rules and len(bad.errors) == 2


def test_a_card_bound_rule_follows_the_chat_s_character_name(migrated, tmp_path):
    rules = tmp_path / "rules.json"
    rules.write_text(json.dumps({"rules": [
        {"id": "bar", "kind": "block", "role": "char", "start": r"☆ \[", "end": r"\]", "separator": "|",
         "card": "Card A"}]}), encoding="utf-8")
    a, b = SimChat(), SimChat()
    for chat in (a, b):
        chat.user("Go on.")
        chat.reply(BAR)
        chat.user("And then?")  # the reply is accepted once the next turn comes (Phase 1: a provisional tail waits)
    with make_client(migrated, parsers_file=str(rules)) as c:
        sync(c, a, character_name="Card A")
        sync(c, b, character_name="Card B")
        convs = {x["host_chat_ref"]: x["id"] for x in c.get("/v1/conversations").json()}
        state = lambda chat: {s["key"]: s["value"] for s in c.get(f"/v1/conversations/{convs[chat.id]}/state").json()}
        assert state(a)["Level"] == "3" and state(a)["Items"] == "물약 ×2 / 해독제 ×1"
        assert state(b) == {}
    with psycopg.connect(migrated, row_factory=dict_row) as conn:  # a rebuild reads the names as well
        from nmos_sidecar.parsers import load_rules
        rebuild_state(conn, load_rules(str(rules)))
        keys = conn.execute("SELECT c.host_chat_ref, count(*) AS n FROM state_observation s"
                            " JOIN conversation c ON c.id = s.conversation_id GROUP BY 1").fetchall()
    assert {r["host_chat_ref"]: r["n"] for r in keys} == {a.id: 6}


def test_a_bar_ending_at_the_line_s_end_keeps_brackets_inside_a_value():
    ruleset = compile_rules({"rules": [
        {"id": "bar", "kind": "block", "start": r"☆ \[", "end": r"\]\s*$", "separator": "|"}]})
    content = "등대 계단 위.\n***☆ [Location: 항구 마을 [낡은 등대] 꼭대기 | Level: 7]\n[Memo| None ]"
    assert {k: v for _, k, v in parse(ruleset, content, "char", None)} == {
        "Location": "항구 마을 [낡은 등대] 꼭대기", "Level": "7"}
