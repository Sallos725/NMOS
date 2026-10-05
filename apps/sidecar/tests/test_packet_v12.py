"""PHASE-31 step 2: packet-v12, recall that knows what changed. One deterministic case per rule and its history-cue
exception (Q1–Q4, `docs/phases/PHASE-31.md`), and packet-v11 unchanged. The rows and messages are synthetic, shaped
like the PHASE-28 gate's misses: an excerpt of a replaced value (S1 turn 240, 03/05), an ended role on a question about
now (02), and the lent-book anchor that tied on the question's keywords (K43)."""

from __future__ import annotations

from typing import Iterator
from uuid import UUID

import pytest

from conftest import make_client
from memeval import _sync, settings_for
from nmos_sidecar import audit
from nmos_sidecar.facts import FIRST_CUE, HISTORY_CUE
from nmos_sidecar.packet import CHANGE_POLICIES, POLICIES, grown_excerpt
from nmos_sidecar.retrieval import CALLED, WHERE
from nmos_sidecar.retrieval import (RecallOptions, asks_about_old, ended_role_kept, keywords, named_facts, one_char_words,
                                    replaced_marks, replaced_values, states_marked, states_replaced)
from simchat import SimChat
from test_packet_ledger import db, extract

# --- Q4: the history cue --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("message", ["전에 어디 살았지?", "이전에 뭐라고 불렀어?", "예전에 살던 집", "원래 어디 있었어?",
                                     "처음에 뭐 했지?", "Where did she live before?", "What name was he used to calling her?",
                                     "Where was it previously?", "Who had it at first?", "윤슬포 첫날 저녁에 뭐 먹었지?",
                                     "첫 날 어디서 잤어?"])
def test_the_history_cue(message):
    assert HISTORY_CUE.search(message)


@pytest.mark.parametrize("message", ["지금 어디 살아?", "첫눈 왔다", "하람이는 지금 어디 있어?", "요즘 뭐 해?", "Where does she live now?",
                                     "beforehand, hi"])
def test_not_the_history_cue(message):
    assert not HISTORY_CUE.search(message)


def test_the_history_cue_holds_the_first_cue():
    assert FIRST_CUE.pattern in HISTORY_CUE.pattern


def test_the_policy_is_registered_and_v11_is_not_a_change_policy():
    assert "packet-v12" in POLICIES and CHANGE_POLICIES == {"packet-v12"}


# --- Q3: the excerpt's anchor breaks a tie on the question's one-character words --------------------------------------

LENT = "이안이 빌려준 책 제목이 뭐였지?"
LENDING = " ".join([
    "비가 그치자 항구가 조용해졌다.", "이안이 고개를 숙이고 빌려준 날이 뭐였는지 떠올렸다.", "갈매기가 울었다.",
    "고양이가 졸았다.", "파도가 밀려왔다.", "등불이 켜졌다.", "바람이 불었다.", "배가 들어왔다.",
    "백이안이 책 한 권을 빌려준다며 건넸다.", "표지에는 『북해 조류 일지』라고 적혀 있었다.", "밤이 깊었다."])


def test_one_character_words_are_the_questions_and_never_a_lone_latin_letter():
    assert one_char_words(LENT) == ("책",)
    assert one_char_words("a 집 I 돈 집") == ("집", "돈")
    assert one_char_words("3 번 방 _ x") == ("3", "번", "방")  # a digit is a word; a lone Latin letter or _ is not
    assert "책" not in keywords(LENT)  # what `keywords` drops, the tie-break keeps


def test_a_tie_on_the_keywords_goes_to_the_sentence_with_the_one_character_word():
    words = keywords(LENT)
    v11, _ = grown_excerpt(LENDING, " ".join(words), words, 400)
    v12, _ = grown_excerpt(LENDING, " ".join(words), words, 400, tie_words=one_char_words(LENT))
    assert "북해 조류 일지" not in v11  # the anchor tied at three keywords and went to "이안이 고개를 숙이고…"
    assert "백이안이 책 한 권을" in v12 and "북해 조류 일지" in v12


def test_the_one_character_word_never_outranks_a_keyword():
    words = keywords(LENT)
    more = LENDING.replace("떠올렸다.", "제목을 떠올렸다.")  # the first sentence now holds four keywords
    text, _ = grown_excerpt(more, " ".join(words), words, 400, tie_words=one_char_words(LENT))
    assert "제목을 떠올렸다" in text


# --- Q1: an excerpt of a replaced value -----------------------------------------------------------------------------


def lives(position, value, history=()):
    return {"position": position, "turn": position // 2, "subject": "윤하람", "subject_type": "character",
            "predicate": "located_in", "object": value, "value": None, "polarity": "positive",
            "history": list(history)}


def moved():
    old = {"position": 30, "turn": 15, "predicate": "located_in", "subject": "윤하람", "object": "갈매기 여관",
           "value": None, "polarity": "positive", "outcome": "superseded"}
    return lives(400, "제과학교 기숙사", [old, {**old, "position": 400, "turn": 200, "object": "제과학교 기숙사",
                                             "outcome": "current"}])


def test_an_earlier_excerpt_of_the_replaced_value_is_one():
    replaced = replaced_values([moved()])
    assert replaced == [(200, ("갈매기 여관",), ("제과학교 기숙사",))]
    assert states_replaced("하람은 갈매기 여관 2층에서 내려왔다.", 16, replaced, ("윤하람",))


def test_an_excerpt_holding_the_current_value_or_after_it_or_without_the_old_one_is_not():
    replaced = replaced_values([moved()])
    assert not states_replaced("갈매기 여관을 떠나 제과학교 기숙사로 짐을 옮겼다.", 16, replaced)
    assert not states_replaced("하람은 갈매기 여관 앞을 지나갔다.", 210, replaced)  # after the current version
    assert not states_replaced("하람은 빵을 구웠다.", 16, replaced)
    assert not states_replaced("하람은 갈매기 여관 2층에서 내려왔다.", None, replaced)


def test_a_name_shared_with_the_old_value_is_not_its_span():
    # an old value that is mostly a name: an excerpt naming the person alone does not repeat it
    old = {"position": 10, "turn": 5, "predicate": "addresses", "subject": "윤하람", "object": "서도윤",
           "value": "도윤 씨", "polarity": "positive", "outcome": "superseded"}
    f = {**old, "position": 300, "turn": 150, "value": "도도", "outcome": None, "history": [old]}
    replaced = replaced_values([f])
    assert not states_replaced("서도윤은 고개를 끄덕였다.", 20, replaced, ("서도윤", "도윤"))


def test_only_a_superseded_version_of_the_same_predicate_counts():
    f = moved()
    f["history"][0] = {**f["history"][0], "predicate": "event"}
    assert replaced_values([f]) == []
    f["history"][0] = {**f["history"][0], "predicate": "located_in", "outcome": "ended"}
    assert replaced_values([f]) == []


# --- Q1 amended (2026-10-05, the reduced live gate): marks, and the facts the question names -------------------------

NAMES = frozenset({"서도윤", "도윤", "윤하람", "하람", "백이안", "이안"})


def addressed(position, value, history=(), subject="백이안", obj="서도윤"):
    return {"position": position, "turn": position // 2, "subject": subject, "subject_type": "character",
            "object": obj, "object_type": "character", "predicate": "addresses", "value": value,
            "polarity": "positive", "history": list(history)}


def old(position, value, predicate="addresses", obj="서도윤"):
    return {"position": position, "turn": position // 2, "predicate": predicate, "object": obj, "value": value,
            "outcome": "superseded"}


def test_a_quoted_old_form_is_a_mark_and_a_bare_name_is_none():
    f = addressed(400, "반말, '도윤'이라고 부름", [old(14, "존댓말, '서 선생'이라고 부름")])
    marks = replaced_marks([f], NAMES)
    assert marks == [(200, {"서선생"}, set(), set(), set())]  # '도윤' is only a name: no mark of the current version
    said = "\"비밀 동지끼리 '서 선생', '백 서기님'은 좀 멀지 않아요? 이제 서로 이름으로 부르죠.\""
    assert states_marked(said, 95, marks)
    assert not states_marked(said, 210, marks)  # after the current version
    assert not states_marked("이안은 도윤을 보며 웃었다.", 95, marks)


def test_an_excerpt_with_the_current_form_is_kept():
    f = addressed(434, "반말, '도도'라고 부름", [old(42, "존댓말, '도윤 씨'라고 부름"), old(214, "반말, '도윤아'라고 부름")],
                  subject="하람")
    marks = replaced_marks([f], NAMES)
    assert states_marked("\"도윤 씨라고 불러 주는 대신, 앞으로 제가 새 빵 만들면\"", 21, marks)
    assert not states_marked("\"도윤 씨 말고 이제 도도라고 할게.\"", 172, marks)


def test_a_place_marks_its_words_with_a_particle_after_them_and_no_prose_word():
    f = lives(440, "수도 한울", [old(40, None, "located_in", "갈매기 여관")])
    marks = replaced_marks([f], NAMES)
    assert marks[0][2] == {"갈매기", "여관"}
    assert states_marked("\"네. 이 여관이 제 집이에요.\"", 17, marks)
    assert not states_marked("여관을 떠나 수도 한울로 갔다.", 100, marks)  # it says the current place
    assert replaced_marks([f], NAMES, places=False) == []  # a place's words only for a question that asks where
    prose = addressed(300, "반말, 편한 말투", [old(40, "존댓말, 친구 사이의 말투")])
    assert replaced_marks([prose], NAMES) == []  # 친구, 말투: no marks


def test_a_question_that_names_the_old_value_asks_about_the_change():
    f = lives(440, "지도방 다락방", [old(40, None, "located_in", "갈매기 여관")])
    assert asks_about_old(f, "도윤은 왜 여관에서 나왔어?", NAMES)
    assert not asks_about_old(f, "지금 어디 살아?", NAMES)
    assert not asks_about_old(f, "왜 다락방에 갔어?", NAMES)  # the current value


def test_a_form_of_address_marks_only_a_question_about_what_someone_is_called():
    f = addressed(400, "반말, '도윤'이라고 부름", [old(14, "존댓말, '서 선생'이라고 부름")])
    assert replaced_marks([f], NAMES, calls=False) == []
    assert CALLED.search("이안은 도윤을 뭐라고 부르지?") and CALLED.search("하람이는 도윤을 뭐라고 불러?")
    assert not CALLED.search("무진 선장이 도윤한테 했던 약속, 지키고 있어?")


def test_the_where_cue():
    assert WHERE.search("하람이는 지금 어디 있어?") and WHERE.search("Where does she live now?")
    assert not WHERE.search("교직원 식당 주방에서 고친 게 뭐였어?")


def test_the_facts_a_question_names_judge_too():
    pair = addressed(400, "반말, '도윤'이라고 부름", [old(14, "존댓말, '서 선생'이라고 부름")])
    other = addressed(300, "존댓말, '선장님'이라고 부름", [old(10, "존댓말, '아저씨'라고 부름")], subject="서도윤",
                      obj="강무진")
    place = lives(440, "수도 한울", [old(40, None, "located_in", "갈매기 여관")])
    given = {"백이안": frozenset({"이안"}), "서도윤": frozenset({"도윤"}), "윤하람": frozenset({"하람"})}
    assert named_facts([pair, other, place], "이안은 도윤을 뭐라고 부르지?", None, given) == [pair]
    assert named_facts([pair, other, place], "하람이는 지금 어디 있어?", None, given) == [place]  # a place: its subject
    assert named_facts([pair], "이안은 뭐 해?", None, given) == []  # one of the pair


# --- Q2: an ended role ----------------------------------------------------------------------------------------------


def role(subject, obj, value, polarity="positive", position=100):
    return {"position": position, "turn": position // 2, "subject": subject, "subject_type": "character",
            "object": obj, "object_type": "character", "predicate": "role_toward", "value": value,
            "polarity": polarity}


def test_an_ended_role_is_kept_when_nothing_about_the_pair_is_current_and_both_are_named():
    ended = role("서도윤", "오봉순", "투숙객: 갈매기 여관 3호실에 묵음", "negative")
    assert ended_role_kept(ended, [ended], "도윤이랑 봉순 사이는 지금 어때? 서도윤 오봉순")
    assert not ended_role_kept(ended, [ended], "서도윤 지금 어디 살아?")  # one of the two
    other = role("오봉순", "서도윤", "단골 손님")
    assert not ended_role_kept(ended, [ended, other], "서도윤이랑 오봉순 사이는 지금 어때?")  # the pair has a current fact
    gone = {**other, "polarity": "negative"}
    assert ended_role_kept(ended, [ended, gone], "서도윤이랑 오봉순 사이는 지금 어때?")


# --- through a request, and its replay under packet-v11 ---------------------------------------------------------------

WINDOW = 4


@pytest.fixture
def v12(migrated: str) -> Iterator[tuple]:
    """Extraction by the memeval stub extractor, no vectors, packet-v12."""
    settings = {k: v for k, v in settings_for("full").items() if not k.startswith("embed_")} | {
        "embed_backfill": 0, "packet_policy": "packet-v12"}
    with make_client(migrated, **settings) as c:
        yield c, migrated


def a_move(client, url) -> SimChat:
    """Hana lived in the lighthouse and moved to the bakery; both messages are long out of the window."""
    chat = SimChat()
    chat.reply("Welcome to the story.")
    for user in ("Hana moved to the lighthouse.", "Hana sleeps in the lighthouse tower and polishes the lamp nightly.",
                 *[f"Idle chatter {i} about clouds." for i in range(4)], "Hana moved to the bakery.",
                 *[f"Idle chatter {i} about rain." for i in range(4)]):
        chat.user(user)
        chat.reply("Noted.")
        _sync(client, chat)
    extract(url)
    return chat


def ask(client, chat: SimChat, text: str) -> dict:
    chat.user(text)
    _sync(client, chat)
    return client.post("/v1/retrieve", json={"chat_id": chat.id, "query": text, "previous_ai": "",
                                             "in_context_ids": [m["chatId"] for m in chat.messages[-WINDOW:]],
                                             "budget_tokens": 1500}).json()


def test_a_question_about_now_loses_the_old_excerpt_and_packet_v11_keeps_it(v12):
    client, url = v12
    chat = a_move(client, url)
    out = ask(client, chat, "Where does Hana sleep now?")
    text = out["packet"]["text"]
    assert "Hana located in bakery" in text
    assert "lighthouse tower" not in text
    with db(url) as conn:
        again = audit.replay(conn, UUID(out["trace_id"]), RecallOptions())
        old = audit.replay(conn, UUID(out["trace_id"]), RecallOptions(), policy="packet-v11")
    assert again["reproduced"] is True and again["text"] == text
    trace = client.get(f"/v1/trace/{out['trace_id']}").json()
    assert trace["latency_ms"]["replaced_left_out"] >= 1 and trace["latency_ms"]["ended_left_out"] == 0
    assert "lighthouse tower" in old["text"]


def test_a_question_with_the_history_cue_keeps_the_old_excerpt(v12):
    client, url = v12
    chat = a_move(client, url)
    text = ask(client, chat, "Where did Hana sleep before?")["packet"]["text"]
    assert "lighthouse tower" in text
