"""Owner 2026-11-25: a status window's key prefix leaves what is set up and stored working. One character's window keeps
its bare keys (as at 5260794); a prefix only when one reply holds two characters' windows; a pin or a watch on a bare
key covers the prefixed keys by their last part (`statechange.covered`, `source_time.base`'s convention); a place or a
scene word is never a character. Synthetic names only."""

from __future__ import annotations

import json
import re

import pytest

from conftest import make_client
from nmos_sidecar import parsers, source_time, statechange, statusshape
from nmos_sidecar.statewatch import detect
from simchat import SimChat
from test_sidecar_integration import recall, sync

CARD = "Key compat card"


def shape(*keys, **extra):
    return parsers.compile_rules({"rules": [{"card": CARD, "id": "s", "kind": "shape", "keys": list(keys), **extra}]})


def read(rules, text):
    return {k: v for _, k, v in parsers.parse(rules, text, "char", None, CARD)}


def two(seoyeon_hp=80, minji_hp=50):
    return (f"[서연 | HP: {seoyeon_hp} | MP: 30 | 기분: 맑음]\n"
            f"[민지 | HP: {minji_hp} | MP: 10 | 기분: 흐림]")


# --- the entity rule --------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "[서연 | HP: 80 | MP: 30 | 기분: 맑음]",  # one character's window: bare, as at the base commit
    "[서연 상태창]\nHP: 80\nMP: 30\n기분: 맑음",
    "[서연: HP=80|MP=30|기분=맑음]",
    "[HP: 80 | MP: 30 | 기분: 맑음]\n[HP: 81 | MP: 31 | 기분: 맑음]",  # two windows, no names: the later wins
    "[서연 | HP: 1 | MP: 2 | 기분: 3]\n[서연 | HP: 80 | MP: 30 | 기분: 맑음]",  # one name twice: one character
])
def test_a_window_for_one_character_keeps_bare_keys(text):
    assert set(read(shape("HP", "MP", "기분"), text)) == {"HP", "MP", "기분"}


def test_two_characters_in_one_reply_are_told_apart():
    assert read(shape("HP", "MP", "기분"), two()) == {"서연.HP": "80", "서연.MP": "30", "서연.기분": "맑음",
                                                     "민지.HP": "50", "민지.MP": "10", "민지.기분": "흐림"}


def test_a_window_without_a_name_beside_named_ones_stays_bare():
    text = two() + "\n[HP: 99 | MP: 9 | 기분: 보통]"
    got = read(shape("HP", "MP", "기분"), text)
    assert got["HP"] == "99" and got["서연.HP"] == "80" and got["민지.HP"] == "50"


@pytest.mark.parametrize("text", [
    "[교실 | 날짜: 3일 | 시간: 오후 | 위치: 2층]",
    "[교실 | 날짜: 3일 | 시간: 오후 | 위치: 2층]\n[복도 | 날짜: 3일 | 시간: 밤 | 위치: 1층]",
    "[Classroom | date: day 3 | time: noon | location: 2F]\n[Hall | date: day 3 | time: night | location: 1F]",
    "[교실 | 날씨: 맑음 | 계절: 봄 | 요일: 월]\n[복도 | 날씨: 비 | 계절: 봄 | 요일: 월]",
])
def test_a_place_or_scene_window_is_never_a_character(text):
    keys = statusshape.blocks(text)[0].keys
    assert all("." not in k for k in read(shape(*sorted(keys)), text))


def test_scene_keys_stay_bare_beside_two_characters():
    got = read(shape("HP", "MP", "위치"), "[서연 | 위치: 숲 | HP: 1 | MP: 2]\n[민지 | 위치: 숲 | HP: 3 | MP: 4]")
    assert got == {"위치": "숲", "서연.HP": "1", "서연.MP": "2", "민지.HP": "3", "민지.MP": "4"}
    assert statusshape.scene_only("Status.Date") and statusshape.scene_only("날씨") and not statusshape.scene_only("HP")


def test_two_names_with_no_key_in_common_are_no_characters():
    found = statusshape.blocks("[서연 | HP: 1 | MP: 2 | SP: 3]\n[민지 | 금화: 1 | 은화: 2 | 동화: 3]")
    assert statusshape.characters(found) == [None, None]


def test_a_number_keeps_its_value_and_a_word_list_keeps_its_second_word():
    assert read(shape("HP", "MP", "위치"), "[HP: 80 | 피곤함 | MP: 40 | 위치: 집]")["HP"] == "80"  # as at the base
    assert read(shape("상태", "MP", "위치"), "[상태: 중독 | 출혈 | MP: 40 | 위치: 집]")["상태"] == "중독 | 출혈"


@pytest.mark.parametrize("keys,text", [
    (("HP", "소지품", "MP", "열쇠"), "[HP: 1 | 소지품: [물약: 2 | 열쇠: 1] | MP: 2]"),
    (("HP", "소지품", "열쇠"), "[HP: 1 | 소지품: [물약: 2 | 열쇠: 1]]"),
    (("HP", "MP", "위치", "방어"), "[HP: 80 (버프: 공격 | 방어: 10) | MP: 40 | 위치: 집]"),
])
def test_a_field_inside_a_nested_bracket_stays_a_key_as_before(keys, text):
    """Before nesting was read every `|` split, so these inner fields were stored keys; they still are."""
    assert set(keys) <= set(read(shape(*keys), text))


@pytest.mark.parametrize("text", [
    "【이름: 서연 | 나이: 17 | 직업: 학생 | 상태: [HP: 80 | MP: 40 | 위치: 집]】",
    "[서연]\n나이: 17\n직업: 학생\n현재: [HP: 80 | MP: 40 | 위치: 집]",
    "[상태창]\n나이: 17\n직업: 학생\n현재: [HP: 80 | MP: 40 | 위치: 집]",
])
def test_an_enclosing_new_shape_never_hides_the_one_line_window_inside(text):
    assert read(shape("HP", "MP", "위치"), text) == {"HP": "80", "MP": "40", "위치": "집"}


def test_a_newer_shape_in_the_same_reply_never_overwrites_the_classic_windows_value():
    text = "<div>[HP: 1 | MP: 2 | 위치: 집]</div><div>HP: 5</div><div>MP: 6</div><div>위치: 숲</div>"
    assert len(statusshape.blocks(text)) == 2
    assert read(shape("HP", "MP", "위치"), text) == {"HP": "1", "MP": "2", "위치": "집"}  # as at the base commit


def test_two_places_sharing_a_key_that_is_not_the_scenes_are_told_apart():
    """Pinned as built: the shape cannot tell a place from a character, so two named windows sharing a key that is not
    about the scene are prefixed (the alternative is one overwriting the other); scene keys stay bare."""
    got = read(shape("날짜", "인원", "분위기"), "[교실 | 날짜: 3일 | 인원: 30 | 분위기: 조용]\n"
                                              "[복도 | 날짜: 3일 | 인원: 5 | 분위기: 시끄러움]")
    assert got == {"날짜": "3일", "교실.인원": "30", "교실.분위기": "조용", "복도.인원": "5", "복도.분위기": "시끄러움"}


# --- pins, the change line and watches --------------------------------------------------------------------------------

def test_a_bare_name_covers_a_key_by_its_last_part_and_a_full_name_only_itself():
    assert statechange.covered("HP", {"HP"}) and statechange.covered("서연.HP", {"HP"})
    assert statechange.covered("민지.hp", {"HP"})  # lower-cased and trimmed, as source_time.base
    assert statechange.covered("서연.HP", {"서연.HP"}) and not statechange.covered("민지.HP", {"서연.HP"})
    assert not statechange.covered("HP", {"서연.HP"}) and not statechange.covered("MP", {"HP"})
    for key in ("서연.HP", " Status.Date ", "hp"):
        assert statechange.base(key) == source_time.base(key)  # one convention


def window(position, values):
    return {"position": position, "turn": position, "host_logical_id": f"m{position}", "values": values}


def test_a_pin_on_a_bare_key_makes_every_characters_key_core():
    windows = [window(1, {"서연.HP": "80", "민지.HP": "50", "서연.MP": "30"}),
               window(2, {"서연.HP": "80", "민지.HP": "50", "서연.MP": "30"})]
    told = {t.key for t in statechange.tell(windows, frozenset({"HP"}))}
    assert told == {"서연.HP", "민지.HP"}  # unchanged, but pinned; MP neither changed nor pinned
    assert {t.key for t in statechange.tell(windows, frozenset({"서연.HP"}))} == {"서연.HP"}
    assert statechange.tell(windows) == []


def test_one_character_to_two_is_told_as_new_values_with_no_invented_change():
    """The turn a second character's window appears: the model gets each character's current value, with no change
    mark from the old bare `HP` (nothing says whose it was) and no line saying `HP` was removed."""
    windows = [window(1, {"HP": "80", "MP": "30"}), window(2, {"HP": "70", "MP": "30"}),
               window(3, {"서연.HP": "70", "서연.MP": "30", "민지.HP": "50", "민지.MP": "10"})]
    told = statechange.tell(windows, frozenset({"HP"}))
    assert [(t.key, t.value, t.since_previous) for t in told] == [
        ("서연.HP", "70", None), ("민지.HP", "50", None), ("서연.MP", "30", None), ("민지.MP", "10", None)]
    assert all(t.key != "HP" for t in told)
    back = statechange.tell([*windows, window(4, {"HP": "65", "MP": "30"})], frozenset({"HP"}))
    assert [(t.key, t.value, t.since_previous) for t in back] == [("HP", "65", None), ("MP", "30", None)]


def entry(value, position):
    return {"value": value, "position": position, "last_position": position, "turn": position, "rule_id": "s",
            "revision_id": position, "redone": False}


def test_a_watch_on_a_bare_key_covers_each_characters_key():
    hist = {"서연.HP": [entry("80", 1), entry("60", 2)], "민지.HP": [entry("50", 1), entry("40", 2)],
            "서연.MP": [entry("30", 1), entry("20", 2)]}
    quiet = {2: "둘은 말없이 걸었다."}
    assert {f["key"] for f in detect(hist, {"s": frozenset({"HP"})}, quiet)} == {"서연.HP", "민지.HP"}
    assert {f["key"] for f in detect(hist, {"s": frozenset({"서연.HP"})}, quiet)} == {"서연.HP"}
    assert detect(hist, {"s": frozenset({"HP"})}, {2: "서연의 HP가 60으로, 민지는 40으로 줄었다."}) == []


# --- through the sidecar --------------------------------------------------------------------------------------------

@pytest.fixture
def shape_rules(tmp_path):
    def make(**extra):
        path = tmp_path / "rules.json"
        path.write_text(json.dumps({"rules": [{"card": CARD, "id": "s", "kind": "shape", "role": "char",
                                               "keys": ["HP", "MP", "기분"], **extra}]}), encoding="utf-8")
        return str(path)
    return make


def chat_of(*replies):
    chat = SimChat()
    for reply in replies:
        chat.user("계속.")
        chat.reply(reply)
    chat.user("다음.")
    return chat


def test_a_pin_set_on_a_bare_key_still_tells_both_characters(migrated, shape_rules):
    chat = chat_of(two(), two(), two())
    with make_client(migrated, parsers_file=shape_rules(), packet_policy="packet-v18") as c:
        sync(c, chat, character_name=CARD)
        before = recall(c, chat, "다음.", budget=1200)["packet"]["text"]
        assert 'key="서연.HP"' not in before  # unchanged and not core
        assert c.put("/v1/parsers/card/pins", json={"card": CARD, "keys": ["HP"]}).json()["pins"] == ["HP"]
        text = recall(c, chat, "다음.", budget=1200)["packet"]["text"]
    assert re.search(r'<Item key="서연\.HP"[^>]*>80</Item>', text) and re.search(r'<Item key="민지\.HP"[^>]*>50</Item>', text)
    assert 'key="서연.MP"' not in text


def test_a_single_characters_chat_stores_the_keys_it_stored_before(migrated, shape_rules):
    from nmos_sidecar.state import history

    chat = chat_of("[서연 | HP: 80 | MP: 30 | 기분: 맑음]", "[서연 | HP: 60 | MP: 30 | 기분: 맑음]")
    path = shape_rules()
    with make_client(migrated, parsers_file=path, packet_policy="packet-v18") as c:
        sync(c, chat, character_name=CARD)
        conv = c.get("/v1/conversations").json()[0]["id"]
    version = parsers.load_rules(path).version
    import psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(migrated, row_factory=dict_row) as conn:
        head = conn.execute("SELECT head_commit_id FROM conversation WHERE id = %s", (conv,)).fetchone()["head_commit_id"]
        assert set(history(conn, head, version)) == {"HP", "MP", "기분"}


def test_a_watch_on_a_bare_key_flags_each_characters_number(migrated, shape_rules):
    chat = chat_of(two(80, 50), two(60, 50))  # 서연's HP falls and the story never says so
    with make_client(migrated, parsers_file=shape_rules(watch=["HP"]), packet_policy="packet-v18") as c:
        sync(c, chat, character_name=CARD)
        conv = c.get("/v1/conversations").json()[0]["id"]
        html = c.get(f"/v1/inspector/c/{conv}?lang=en").json()["html"]
    assert "서연.HP: 80 → 60" in html and html.count("state_dismiss:") == 1
