"""PHASE-39 steps 3–4: a status window's history along the head, its lanes, its recall line and its flags."""

from __future__ import annotations

import json
import re
import zipfile

import psycopg
import pytest
from psycopg.rows import dict_row

from conftest import make_client
from nmos_sidecar.parsers import load_rules
from nmos_sidecar.state import history
from simchat import SimChat
from test_sidecar_integration import sync

RULE = {"id": "bar", "kind": "block", "role": "char", "start": r"☆ \[", "end": r"\]\s*$", "separator": "|"}


def bar(level: int, gold: int, items: str = "물약 ×2", prose: str = "길을 걷는다.") -> str:
    return f"{prose}\n☆ [Level: {level} | Gold: {gold} | Items: {items}]"


@pytest.fixture
def rules(tmp_path):
    def write(*extra: dict) -> str:
        path = tmp_path / "rules.json"
        path.write_text(json.dumps({"rules": [{**RULE, **e} for e in extra] or [RULE]}), encoding="utf-8")
        return str(path)
    return write


def read(url: str, chat: SimChat, path: str, **kw) -> dict:
    with psycopg.connect(url, row_factory=dict_row) as conn:
        head = conn.execute("SELECT head_commit_id FROM conversation WHERE host_chat_ref = %s", (chat.id,)).fetchone()
        return history(conn, head["head_commit_id"], load_rules(path).version, **kw)


def values(h: dict, key: str) -> list[tuple[int, int, str]]:
    return [(e["turn"], e["last_turn"], e["value"]) for e in h.get(key, [])]


def test_history_folds_restated_values_and_follows_the_head(migrated, rules):
    path = rules()
    chat = SimChat()
    chat.user("시작.")
    chat.reply(bar(1, 100))
    chat.user("계속.")
    chat.reply(bar(1, 100))  # restated: the same entry
    chat.user("싸운다.")
    chat.reply(bar(2, 150))
    chat.user("쉰다.")
    chat.reply(bar(2, 90))  # a provisional tail: not state until the next turn
    with make_client(migrated, parsers_file=path) as c:
        sync(c, chat)
        h = read(migrated, chat, path)
        assert values(h, "Level") == [(0, 1, "1"), (2, 2, "2")]
        assert values(h, "Gold") == [(0, 1, "100"), (2, 2, "150")]
        assert values(h, "Items") == [(0, 2, "물약 ×2")]
        assert not any(e["redone"] for es in h.values() for e in es)  # not asked for

        chat.user("다음.")
        sync(c, chat)
        assert values(read(migrated, chat, path, keys=["Gold"]), "Gold") == [(0, 1, "100"), (2, 2, "150"), (3, 3, "90")]

        # A reroll of the turn-2 reply: the head's path holds the new bar, marked redone (it holds swipes, H4).
        chat.messages[-3:] = []  # back to the turn-2 reply as the tail
        chat.reroll(bar(2, 120))
        chat.user("다음.")
        sync(c, chat)
        h = read(migrated, chat, path, keys=["Gold"], redone=True)
        assert values(h, "Gold") == [(0, 1, "100"), (2, 2, "120")]
        assert [e["redone"] for e in h["Gold"]] == [False, True]

        # Swiping back to the first answer follows the head too.
        chat.messages.pop()
        chat.swipe(0)
        chat.user("다음.")
        sync(c, chat)
        assert values(read(migrated, chat, path, keys=["Gold"]), "Gold") == [(0, 1, "100"), (2, 2, "150")]

        # An edit of an older bar is a new revision of that message: redone, and the history follows it.
        chat.edit(1, bar(1, 80))
        sync(c, chat)
        h = read(migrated, chat, path, keys=["Gold"], redone=True)
        assert values(h, "Gold") == [(0, 0, "80"), (1, 1, "100"), (2, 2, "150")]
        assert h["Gold"][0]["redone"] and not h["Gold"][1]["redone"]


# --- 3a: the lanes -----------------------------------------------------------------------------------------------

def entries(*spec: tuple[int, str]) -> list[dict]:
    return [{"turn": turn, "last_turn": turn, "value": value} for turn, value in spec]


def test_status_lanes_draw_changes_and_fold_what_never_changed():
    from nmos_sidecar import inspector, timeline
    from test_inspector_timeline import panel_safe

    t = inspector._tl_t("en")
    hist = {"Gold": entries((0, "100"), (2, "150"), (5, "90")), "Level": entries((0, "1"), (4, "2")),
            **{f"Field{i}": entries((0, "same")) for i in range(8)}}
    page = timeline.status(t, hist, 6, None, "", link=lambda turn: f"/inspector/c/c1/t/{turn}")
    lanes = re.findall(r'<span class="tl-k">([^<]+)</span>(?:<span class="tl-val">([^<]*)</span>)?', page)
    assert lanes[:2] == [("Gold", "90"), ("Level", "2")]  # the latest change first, the value now beside it
    fold = page.split('<details class="tl-fold">')[1]
    assert "Unchanged fields (8)" in fold and fold.count('class="tl-k"') == 8
    gold = page.split('<span class="tl-k">Gold</span>')[1].split("</div></div>")[0]
    assert re.findall(r'href="([^"]+)"', gold) == ["/inspector/c/c1/t/0", "/inspector/c/c1/t/2", "/inspector/c/c1/t/5"]
    assert 'data-row="Open that turn"' in page and page.endswith(timeline.SCRIPT)

    part = inspector.conversation_status(hist, 6, "en")
    panel_safe(part)
    assert 'class="tl-bar past" data-v="100" data-s="t0 – t1" data-o="superseded" data-l="0.0"' in part
    assert "href=" not in part.split('class="tl-main"')[1]  # a tap shows the detail; no link in the panel

    few = timeline.status(t, {"Gold": entries((0, "1")), "Level": entries((0, "1"), (1, "2"))}, 3, None, "",
                          link=str)
    assert "tl-fold" not in few  # few keys: nothing folds away

    busy = timeline.status(t, {"HP": entries(*((i, str(i)) for i in range(200)))}, 199, None, "", link=str)
    assert busy.count('class="tl-bar') == timeline.STATUS_BARS and "last 120 values" in busy


def test_the_conversation_page_and_the_panel_show_the_status_lanes(migrated, rules):
    from test_inspector_timeline import panel_safe

    path = rules()
    chat = SimChat()
    for level, gold in ((1, 100), (1, 120), (2, 120)):
        chat.user("계속.")
        chat.reply(bar(level, gold))
    chat.user("다음.")
    with make_client(migrated, parsers_file=path) as c:
        sync(c, chat)
        conv = c.get("/v1/conversations").json()[0]["id"]
        page = c.get(f"/inspector/c/{conv}?lang=en").text
        assert '<a href="#s-status">Status over time <span class="n">2</span></a>' in page  # Gold and Level changed
        section = page.split('<details id="s-status" open>')[1].split("</details>\n")[0]
        assert f'href="/inspector/c/{conv}/t/1?lang=en"' in section and "tl-bar" in section

        embed = lambda q: c.get(f"/v1/inspector/c/{conv}{q}").json()["html"]
        assert 's-status' not in embed("") and 's-status' not in embed("?timeline=lazy")  # a plugin that cannot fill it
        assert '<details id="s-status"><summary><h2>상태창 변화</h2></summary>' \
               '<div class="tl-lazy tl-status"></div></details>' in embed("?timeline=lazy&status=lazy")
        part = embed("?part=status&span=recent")
        panel_safe(part)
        assert "tl-bar" in part and "<b>최근 25턴</b>" in part


# --- 4: the flags --------------------------------------------------------------------------------------------------

def test_what_a_flag_is_and_what_the_story_explains():
    from nmos_sidecar.statewatch import Prose, changes, items

    quiet = Prose("길을 걷는다.")
    assert items("물약 ×2 / 해독제 ×1") == {"물약": "물약 ×2", "해독제": "해독제 ×1"}
    assert items("120/150") is None and items("1,500 G") is None and items("없음") == {}
    assert changes("Items", "물약 ×2", "물약 ×2 / 해독제 ×1", quiet) == [("added", "해독제")]
    assert changes("Items", "물약 ×2", "물약 ×2 / 해독제 ×1", Prose("해독제를 주웠다.")) == []
    assert changes("Items", "물약 ×2 / 해독제 ×1", "물약 ×2", quiet) == [("dropped", "해독제")]
    assert changes("Items", "없음", "단검", quiet) == [("added", "단검")]
    assert changes("Items", "회복 물약(소) x3", "회복 물약(소) x2", Prose("물약을 마셨다.")) == []  # one word names it
    assert changes("Items", "물약 ×2 / 해독제 ×1", "물약 ×1 / 해독제 ×1", quiet) == [("number", "물약")]
    assert changes("Place", "숲", "마을", quiet) == []  # one word for another: a place, not a list
    assert changes("Gold", "100", "150", quiet) == [("number", None)]
    assert changes("Gold", "100", "150", Prose("50골드를 받았다.")) == []  # the difference
    assert changes("Gold", "1,500", "1,450", Prose("Gold를 썼다.")) == []  # the key
    assert changes("HP", "120/150", "100/150", Prose("20의 피해를 입었다.")) == []
    assert changes("HP", "120/150", "100/150", Prose("120의 공격력")) == [("number", None)]  # not 100, not 20
    assert changes("HP", "120/150", "1200/150", Prose("120")) == [("number", None)]
    # measured on the owner's chats (PHASE-39 step 4): a place is not a count, and money is written in words
    assert changes("Place", "여관 2층 객실", "여관 2층 복도", quiet) == []
    assert changes("Place", "B-3 구역", "B-4 구역", quiet) == [("number", None)]  # only the number changed
    assert changes("Money", "1,200,000 원", "1,500,000 원", Prose("상금으로 삼십만 원을 받았다!")) == []
    assert changes("Money", "3,000", "6,000", Prose("3천 골드를 받았다.")) == []
    assert changes("Money", "100,000,000", "220,000,000", Prose("1억 2천만 원")) == []
    assert changes("Money", "100", "130", Prose("천천히 걸었다. 백사장 7번 부두.")) == [("number", None)]  # no amount
    assert changes("SP", "70 / 90", "60 / 90", Prose("A response came.")) == [("number", None)]  # not a word: "sp"
    assert changes("SP", "70 / 90", "60 / 90", Prose("SP가 줄었다.")) == []


def test_a_revert_the_story_names_is_no_flag():
    from nmos_sidecar.statewatch import detect

    def entry(value, position, redone=False):
        return {"value": value, "position": position, "last_position": position, "turn": position, "rule_id": "bar",
                "revision_id": position, "redone": redone}
    hist = {"Place": [entry("성문 앞", 1), entry("빵집", 2), entry("성문 앞", 3, redone=True)],
            "SP": [entry("70 / 90", 1), entry("90 / 90", 2), entry("70 / 90", 3, redone=True)]}
    watch = {"bar": frozenset({"Place", "SP"})}
    before = "빵집에서 쉬며 SP를 채웠다."
    found = detect(hist, watch, {2: before, 3: "해가 뜨자 성문 앞으로 걸어갔다."})
    assert [(f["key"], f["reason"]) for f in found] == [("SP", "reverted")]
    assert detect(hist, watch, {2: before, 3: "SP가 70으로 줄었다. 성문 앞."}) == []


def test_a_watched_key_is_flagged_dismissed_and_back_on_undo(migrated, rules):
    path = rules({"watch": ["Gold", "Items"]})
    chat = SimChat()
    chat.user("시작.")
    chat.reply(bar(1, 100))
    chat.user("걷는다.")
    chat.reply(bar(1, 100, "물약 ×2 / 해독제 ×1"))  # (i): nothing gave it
    chat.user("싸운다.")
    chat.reply(bar(2, 150, "물약 ×2 / 해독제 ×1", "고블린을 쓰러뜨리고 50골드를 얻었다."))  # explained; Level unwatched
    chat.user("쉰다.")
    chat.reply(bar(2, 130, "물약 ×2 / 해독제 ×1"))  # (ii)
    chat.user("다음.")
    with make_client(migrated, parsers_file=path) as c:
        sync(c, chat)
        conv = c.get("/v1/conversations").json()[0]["id"]
        html = c.get(f"/v1/inspector/c/{conv}?lang=en").json()["html"]
        flagged = re.findall(r'data-repair="state_dismiss:([0-9a-f]{16})"', html)
        assert len(flagged) == 2
        assert "a status item added that the reply never mentions" in html and "Items: 물약 ×2 → 물약 ×2 / 해독제 ×1 (해독제)" in html
        assert "a status number changed without the reply saying so" in html and "Gold: 150 → 130" in html

        res = c.post(f"/v1/conversations/{conv}/repairs", json={"kind": "state_dismiss", "item": flagged[0]})
        assert res.status_code == 200, res.text
        assert res.json()["applied"] == flagged[0] and res.json()["repair"]["target"]["text"].startswith("Items:")
        again = c.post(f"/v1/conversations/{conv}/repairs", json={"kind": "state_dismiss", "item": flagged[0]})
        assert again.status_code == 422  # already dismissed
        html = c.get(f"/v1/inspector/c/{conv}?lang=en").json()["html"]
        assert re.findall(r'data-repair="state_dismiss:([0-9a-f]{16})"', html) == flagged[1:]
        assert "a repair that matches nothing now" not in html and "status flag dismissed" in html

        c.post(f"/v1/conversations/{conv}/repairs/{res.json()['repair']['id']}/remove")
        html = c.get(f"/v1/inspector/c/{conv}?lang=en").json()["html"]
        assert re.findall(r'data-repair="state_dismiss:([0-9a-f]{16})"', html) == flagged

    unwatched = rules()  # the same rules without `watch`: the same version, nothing flagged
    assert load_rules(unwatched).version == load_rules(path).version
    from nmos_sidecar.parsers import compile_rules
    two = lambda **extra: compile_rules({"rules": [RULE, {**RULE, "id": "other", **extra}]})
    broken = two(watch="Gold")  # not a list: the rule is left out, and that counts (it is read again once fixed)
    assert broken.errors and len(broken.rules) == 1
    assert broken.version != two(watch=["Gold"]).version == two().version
    with make_client(migrated, parsers_file=unwatched) as c:
        assert 'data-repair="state_dismiss:' not in c.get(f"/v1/inspector/c/{conv}?lang=en").json()["html"]


def test_a_value_back_to_the_one_before_after_a_reroll_is_flagged(migrated, rules):
    path = rules({"watch": ["Gold"]})
    chat = SimChat()
    chat.user("시작.")
    chat.reply(bar(1, 100))
    chat.user("고블린을 잡는다.")
    chat.reply(bar(1, 150, prose="50골드를 얻었다."))
    chat.user("쉰다.")
    chat.reply(bar(1, 150, prose="쉰다."))
    chat.reroll(bar(1, 100, prose="쉰다."))  # the rerolled reply forgot the turn before
    chat.user("다음.")
    with make_client(migrated, parsers_file=path) as c:
        sync(c, chat)
        conv = c.get("/v1/conversations").json()[0]["id"]
        html = c.get(f"/v1/inspector/c/{conv}?lang=en").json()["html"]
        assert "back to an earlier value in a rerolled, swiped or edited reply" in html and "Gold: 150 → 100" in html
        assert html.count("state_dismiss:") == 1  # the reverted value, not also as a number change

    plain = SimChat()  # the same values without the reroll: a number the story does not explain
    for prose, gold in (("시작.", 100), ("50골드를 얻었다.", 150), ("쉰다.", 100)):
        plain.user("계속.")
        plain.reply(bar(1, gold, prose=prose))
    plain.user("다음.")
    with make_client(migrated, parsers_file=path) as c:
        sync(c, plain)
        conv = next(x["id"] for x in c.get("/v1/conversations").json() if x["host_chat_ref"] == plain.id)
        html = c.get(f"/v1/inspector/c/{conv}?lang=en").json()["html"]
        assert "back to an earlier value" not in html and "a status number changed" in html


def test_an_archive_made_at_schema_0028_restores_into_0029(migrated, database_url_factory, tmp_path):
    from nmos_sidecar import archive
    from test_archive import play
    from test_restore import client as archive_client, export_to, rewrite

    with archive_client(migrated) as c:
        play(c, migrated)  # a repair among everything else

    def at_0028(name, data):
        if name != "manifest.json":
            return data
        m = json.loads(data)
        m["schema"]["migrations"] = [x for x in m["schema"]["migrations"] if x["version"] < "0029"]
        m["schema"]["level"] = m["schema"]["migrations"][-1]["version"]
        return json.dumps(m).encode()

    old = rewrite(export_to(tmp_path, migrated, "all"), tmp_path / f"old{archive.SUFFIX}", at_0028)
    assert json.loads(zipfile.ZipFile(old).read("manifest.json"))["schema"]["level"] == "0028_reveal_checks.sql"
    target = database_url_factory()
    done = archive.restore_file(target, str(old))
    assert done.migrated == ["0029_state_dismiss.sql"]
    with psycopg.connect(target) as conn, psycopg.connect(migrated) as source:
        mine = conn.execute("SELECT kind, target FROM owner_repair ORDER BY id").fetchall()
        assert mine and mine == source.execute("SELECT kind, target FROM owner_repair ORDER BY id").fetchall()
        conn.execute("INSERT INTO owner_repair (id, conversation_id, kind, target) SELECT gen_random_uuid(),"
                     " conversation_id, 'state_dismiss', '{}' FROM owner_repair LIMIT 1")  # the new kind is allowed


# --- 3b: packet-v17 ------------------------------------------------------------------------------------------------

def test_a_question_about_a_key_s_changes_gets_its_history_under_packet_v17(migrated, rules):
    from test_sidecar_integration import recall

    path = rules()
    chat = SimChat()
    for level, gold in ((1, 100), (1, 120), (2, 120), (2, 90), (2, 95), (3, 95), (3, 60), (3, 61), (4, 61)):
        chat.user("계속.")
        chat.reply(bar(level, gold))
    chat.user("다음.")
    tail = [m["chatId"] for m in chat.messages[-4:]]  # the last bars are in the prompt; the line counts them anyway
    with make_client(migrated, parsers_file=path, packet_policy="packet-v17") as c:
        sync(c, chat)
        out = recall(c, chat, "골드 언제 이렇게 줄었지?", in_context=tail, budget=1200)
        text = out["packet"]["text"]
        line = '<StateHistory key="Gold"><At turn="1">120</At><At turn="3">90</At><At turn="4">95</At>' \
               '<At turn="6">60</At><At turn="7">61</At></StateHistory>'
        assert line.replace('<At turn="1">120</At>', '<At turn="0">100</At><At turn="1">120</At>') in text  # 6 at most
        assert "<Item " not in text  # the last bar is in the prompt: no current value repeated, the history still there
        whole = recall(c, chat, "골드 언제 이렇게 줄었지?", budget=1200)["packet"]["text"]
        assert whole.index("<StateHistory") < whole.index("<Item ")  # first: the message asked for it
        trace = c.get(f"/v1/trace/{out['trace_id']}").json()
        assert trace["latency_ms"]["placed"]["state_history"] == 1
        assert [e["label"] for e in trace["lines"] if e["kind"] == "state_history"] == ["required"]
        assert c.get(f"/v1/trace/{out['trace_id']}/replay").json()["reproduced"] is True

        assert "<StateHistory" not in recall(c, chat, "골드가 얼마 있지?", in_context=tail)["packet"]["text"]  # no cue
        assert "<StateHistory" not in recall(c, chat, "언제 끝나?", in_context=tail)["packet"]["text"]  # no key
        both = recall(c, chat, "Level이랑 골드 언제 바뀌었어?", in_context=tail, budget=1200)["packet"]["text"]
        assert both.index('<StateHistory key="Level">') < both.index('<StateHistory key="Gold">')
    with make_client(migrated, parsers_file=path, packet_policy="packet-v16") as c:
        assert "<StateHistory" not in recall(c, chat, "골드 언제 이렇게 줄었지?", in_context=tail)["packet"]["text"]


def test_asked_keys_words_and_boundaries():
    from nmos_sidecar.retrieval import STATE_CHANGE_CUE, asked_keys

    keys = ["Level", "HP", "MP", "Items", "Stat Points", "하나.기분", "소지금"]
    assert asked_keys("레벨 언제 올랐어?", keys) == ["Level"]  # the bar in English, the chat in Korean
    assert asked_keys("HP랑 MP 언제 줄었어", keys) == ["HP", "MP"]
    assert asked_keys("스탯 포인트 언제 받았지", keys) == asked_keys("stat points?", keys) == ["Stat Points"]
    assert asked_keys("시간이 얼마나 지났어", keys) == []  # 마나 inside 얼마나 is no word
    assert asked_keys("마나가 언제 줄었지", keys) == ["MP"] and asked_keys("chp", keys) == []
    assert asked_keys("하나 기분 언제부터 이랬어", keys) == ["하나.기분"] and asked_keys("기분 어때", keys) == []
    assert STATE_CHANGE_CUE.search("레벨 언제 올랐어?") and not STATE_CHANGE_CUE.search("레벨이 몇이야?")


# --- found by the pre-0.4.0 audit: rules that hang, restored chats, a name that comes late -------------------------

def test_a_start_that_matches_empty_text_is_refused_and_zero_width_marks_end():
    from nmos_sidecar.parsers import compile_rules, parse, prose

    refused = compile_rules({"rules": [{"id": "x", "kind": "block", "start": "", "end": ""},
                                       {"id": "y", "kind": "block", "start": "^", "end": "$"}]})
    assert not refused.rules and all("start must not match empty text" in e for e in refused.errors)
    looking = compile_rules({"rules": [{"id": "z", "kind": "block", "start": "(?=☆)", "end": "(?=☆)|\\]"}]})
    assert parse(looking, "a ☆ [HP: 3] ☆ [MP: 4] b", "char", None) == []  # ends at once, and the loop ends
    assert prose(looking, "a ☆ [HP: 3] b", "char", None) == "a ☆ [HP: 3] b"


def test_chats_no_append_saw_get_their_state_at_the_next_start(migrated, rules):
    path = rules()
    seen, restored = SimChat(), SimChat()
    for chat in (seen, restored):
        chat.user("시작.")
        chat.reply(bar(1, 100))
        chat.user("다음.")
    with make_client(migrated, parsers_file=path) as c:
        sync(c, seen)
        sync(c, restored)
    with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:  # as a restore writes them
        cid = conn.execute("SELECT id FROM conversation WHERE host_chat_ref = %s", (restored.id,)).fetchone()["id"]
        conn.execute("DELETE FROM state_observation WHERE conversation_id = %s", (cid,))
        conn.execute("DELETE FROM revision_text WHERE source_revision_id IN (SELECT sr.id FROM source_revision sr"
                     " JOIN source_object so ON so.id = sr.source_object_id WHERE so.conversation_id = %s)", (cid,))
        assert conn.execute("SELECT count(*) AS n FROM state_observation").fetchone()["n"] > 0  # the other chat's
    with make_client(migrated, parsers_file=path) as c:
        assert values(read(migrated, restored, path), "Gold") == [(0, 0, "100")]


def test_a_card_bound_rule_reads_a_chat_again_when_its_name_arrives(migrated, rules):
    path = rules({"card": "Card A"})
    chat = SimChat()
    chat.user("시작.")
    chat.reply(bar(1, 100))
    chat.user("다음.")
    with make_client(migrated, parsers_file=path) as c:
        sync(c, chat)  # no character name yet
        assert read(migrated, chat, path) == {}
        sync(c, chat, character_name="Card A")
        assert values(read(migrated, chat, path), "Gold") == [(0, 0, "100")]
        sync(c, chat, character_name="Card B")  # renamed in the host: no longer this card's chat
        assert read(migrated, chat, path) == {}


@pytest.mark.parametrize("interrupted", [False, True], ids=["immediate", "interrupted-restart"])
def test_panel_restore_recovers_card_state_in_an_existing_install(migrated, database_url_factory, rules,
                                                                 monkeypatch, interrupted):
    import base64
    import hashlib
    from nmos_sidecar import api, normtext
    from test_panel_restore import check, restore

    path = rules({"card": "Card A"})
    existing, restored = SimChat(), SimChat()
    for chat, gold in ((existing, 10), (restored, 100)):
        chat.user("시작.")
        chat.reply(bar(1, gold))
        chat.user("다음.")
    with make_client(migrated, parsers_file=path) as source:
        sync(source, restored, character_name="Card A")
        data = source.get("/v1/archive").content
    target = database_url_factory()

    def source_rows():
        with psycopg.connect(target) as conn:
            return conn.execute("SELECT id, content, revision_hash FROM source_revision ORDER BY id").fetchall()

    with make_client(target, parsers_file=path) as client:
        sync(client, existing, character_name="Card A")
        before = read(target, existing, path)
        with psycopg.connect(target) as conn:
            observations = conn.execute("SELECT * FROM state_observation ORDER BY id").fetchall()
        uid = client.post("/v1/archive/uploads", json={"bytes": len(data)}).json()["id"]
        sent = client.put(f"/v1/archive/uploads/{uid}/chunks/0", json={
            "data": base64.b64encode(data).decode(), "sha256": hashlib.sha256(data).hexdigest()})
        assert sent.status_code == 200 and sent.json()["state"] == "received"
        assert check(client, uid)["state"] == "checked"
        with monkeypatch.context() as patch:
            if interrupted:
                def fail_before_state(*args, **kwargs):
                    raise RuntimeError("interrupted before the state backfill")
                patch.setattr(api, "sync_rules", fail_before_state)
            result = restore(client, uid)
        assert result["state"] == "restored"
        saved_sources = source_rows()
        if interrupted:
            assert "next start" in result["detail"]
            with psycopg.connect(target, row_factory=dict_row) as conn:
                assert normtext.missing(conn) == []  # text committed before the injected parsing failure
            assert read(target, restored, path) == {}
        else:
            assert values(read(target, restored, path), "Gold") == [(0, 0, "100")]
        assert read(target, existing, path) == before
    with make_client(target, parsers_file=path) as client:
        assert sync(client, restored, character_name="Card A")["status"] == "noop"
        assert values(read(target, restored, path), "Gold") == [(0, 0, "100")]
        assert read(target, existing, path) == before
    assert source_rows() == saved_sources
    with psycopg.connect(target) as conn:
        after = conn.execute("SELECT * FROM state_observation WHERE id = ANY(%s) ORDER BY id",
                             ([row[0] for row in observations],)).fetchall()
        assert after == observations  # existing positive observations were neither deleted nor replaced


def test_missing_state_scan_crosses_no_match_batches_once(migrated, rules, monkeypatch):
    from nmos_sidecar import state

    path = rules()
    existing, unmatched = SimChat(), SimChat()
    existing.user("시작.")
    existing.reply(bar(1, 10))
    existing.user("다음.")
    for i in range(3):
        unmatched.user(f"말 {i}.")
        unmatched.reply(f"대답 {i}.")
    unmatched.user("다음.")
    with make_client(migrated, parsers_file=path) as client:
        sync(client, existing)
        sync(client, unmatched)
    monkeypatch.setattr(state, "STATE_BACKFILL_BATCH", 2)
    parsed = []
    original = state.write_state

    def record(conn, ruleset, conv_id, revision_id, *args):
        parsed.append(revision_id)
        return original(conn, ruleset, conv_id, revision_id, *args)

    monkeypatch.setattr(state, "write_state", record)
    with psycopg.connect(migrated, row_factory=dict_row) as conn:
        before = conn.execute("SELECT * FROM state_observation ORDER BY id").fetchall()
        expected = conn.execute("SELECT sr.id FROM source_revision sr JOIN source_object so"
                                " ON so.id = sr.source_object_id WHERE so.source_kind = 'message'"
                                " AND NOT EXISTS (SELECT 1 FROM state_observation st WHERE st.source_revision_id = sr.id"
                                " AND st.rules_version = %s) ORDER BY sr.id", (load_rules(path).version,)).fetchall()
        assert len(expected) > 2 * state.STATE_BACKFILL_BATCH
        assert state.sync_rules(conn, load_rules(path)) == 0
        assert parsed == [row["id"] for row in expected]
        assert conn.execute("SELECT * FROM state_observation ORDER BY id").fetchall() == before
