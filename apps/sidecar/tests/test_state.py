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
