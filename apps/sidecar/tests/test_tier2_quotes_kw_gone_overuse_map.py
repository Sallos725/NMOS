"""packet-v21 foundations in the read-side helpers: quotes, keywords, gone, overuse and the memory map.

Each v21 rule sits behind an opt-in switch (`v21=True`, `dedupe_positions=True`, ...); the defaults are packet-v20's and
are pinned here too, so a v20 trace replays to the same packet (ADR 0027).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import psycopg
import pytest
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from conftest import make_client
from nmos_sidecar import gone, keywords, memorymap, overuse, quotes
from simchat import SimChat
from test_memorymap import GUILD, HANA, KAITO, MILL, entity, fact, step, view
from test_phase60_told_views import told_row
from test_sidecar_integration import sync

# --- quotes: when a message asks for words --------------------------------------------------------------------------

ASKS_V20_CASES = [  # test_quotes' cases, which v21 keeps
    ("한솔이 그때 뭐라고 했지?", True),
    ('누가 "등불"이라고 말했어?', True),
    ("What did Ryu say at the dock?", True),
    ("한솔은 지금 어디 있어?", False),
    ("류진은 한솔을 뭐라고 부르지?", False),
    ("류진은 처음에 한솔을 뭐라고 불렀더라?", True),
]

NOT_ASKING_V21 = [  # roleplay turns: narration with dialogue, contractions
    '고개를 끄덕이며 말했다. "알겠어, 내일 광장에서 보자."',
    '"알겠어, 내일 광장에서 보자."',
    "I don't think he's right",
    "I don't think he's right, is he?",
    '"어디 가?" 그가 물었다.',
    "'가지 마.' 이안은 속으로 생각했다.",
]


@pytest.mark.parametrize("query,expected", ASKS_V20_CASES)
def test_v21_keeps_every_question_about_words(query, expected):
    assert quotes.asks_for_words(query, v21=True) is expected
    assert quotes.asks_for_words(query) is expected


@pytest.mark.parametrize("query", NOT_ASKING_V21)
def test_v21_reads_no_question_in_roleplay_dialogue(query):
    assert quotes.asks_for_words(query, v21=True) is False


def test_v20_still_reads_any_quote_or_speaking_verb_as_a_question():
    assert quotes.asks_for_words('고개를 끄덕이며 말했다. "알겠어, 내일 광장에서 보자."')
    assert quotes.asks_for_words('"알겠어, 내일 광장에서 보자."')
    assert quotes.asks_for_words("I don't think he's right")  # "'t think he'" was a quote


def test_v21_a_quoted_phrase_asks_beside_a_recall_cue():
    assert quotes.asks_for_words("'등불'이라는 말 누가 했지?", v21=True)
    assert quotes.asks_for_words("Who said 'the lamp'?", v21=True)
    assert quotes.asks_for_words('"등불" 기억나?', v21=True)
    assert not quotes.asks_for_words('"등불"을 들고 나갔다.', v21=True)


# --- quotes: lines and speakers -------------------------------------------------------------------------------------

NAMES = {"이안": "이안", "도윤": "도윤", "elena": "Elena"}


def speakers(text, v21=True):
    return [(s.words, quotes._speaker(s, NAMES, "char", None, v21=v21)) for s in quotes.quotes_in(text, v21=v21)]


def test_v21_reads_single_quoted_and_short_lines_but_no_contractions():
    assert [s.words for s in quotes.quotes_in("'가지 마.' 그녀가 속삭였다. ‘정말?’", v21=True)] == ["가지 마.", "정말?"]
    assert [s.words for s in quotes.quotes_in('"아니." 이안이 말했다. "죽어"', v21=True)] == ["아니.", "죽어"]
    assert quotes.quotes_in("I don't think he's right. Mira's book.", v21=True) == []
    assert quotes.quotes_in('"아니." "죽어"') == []  # v20: four characters at least
    assert quotes.quotes_in("'가지 마.'") == []  # v20: no single quotes


def test_v21_names_the_speaker_of_the_sentence_before_a_lone_quote():
    assert speakers('이안이 돌아보았다.\n"가지 마."') == [("가지 마.", "이안")]
    assert speakers('이안이 돌아보았다.\n"가지 마."', v21=False) == [("가지 마.", None)]
    # the sentence before holds a quote: an exchange, the other one's turn may be next
    assert speakers('도윤이 이안을 보았다. "가자."\n"싫어."') == [("가자.", "도윤"), ("싫어.", None)]
    # two characters as subjects before: nobody
    assert speakers('이안이 웃자 도윤이 고개를 저었다.\n"가지 마."') == [("가지 마.", None)]


def test_v21_reads_a_clause_whose_other_subjects_are_no_character():
    assert speakers('"걱정 마." 도윤이 목소리가 떨리며 말했다.') == [("걱정 마.", "도윤")]
    assert speakers('"걱정 마." 도윤이 목소리가 떨리며 말했다.', v21=False) == [("걱정 마.", None)]
    assert speakers('"이안, 가자." 도윤이 다가오며 이안이 말했다.') == [("이안, 가자.", None)]  # two characters: nobody
    assert speakers('"걱정 마." 할머니가 말했다.') == [("걱정 마.", None)]  # no known character


def test_v21_reads_english_attribution():
    assert speakers('"Stay here," said Elena. Elena whispered, "Don\'t go." "Fine," Elena said.') == [
        ("Stay here,", "Elena"), ("Don't go.", "Elena"), ("Fine,", "Elena")]
    assert speakers('"Stay here," she said.') == [("Stay here,", None)]
    assert speakers('Then Elena said, "Stay here."') == [("Stay here.", "Elena")]
    assert speakers('"Stay here," said Elena.', v21=False) == [("Stay here,", None)]


def test_v21_pick_uses_the_v21_reading_and_v20_is_unchanged():
    rows = [{"clean": '이안이 돌아보았다.\n"가지 마."\n바람이 불었다.', "position": 4, "turn": 2, "id": "r1",
             "role": "char", "name": None}]
    ask = "바람이 불 때 이안이 뭐라고 했지?"
    assert [(q.words, q.speaker) for q in quotes.pick(rows, ask, NAMES, 10, False, v21=True)] == [("가지 마.", "이안")]
    assert [(q.words, q.speaker) for q in quotes.pick(rows, ask, NAMES, 10, False)] == [("가지 마.", None)]


def test_v21_query_terms_keep_whole_nouns():
    assert quotes.query_terms("윤하나가 주머니에서 뭘 꺼냈지?", v21=True) == {"윤하나": 1.0, "주머니": 1.0, "꺼냈": 0.5}
    assert "윤하" in quotes.query_terms("윤하나가 주머니에서 뭘 꺼냈지?")  # v20's two passes


# --- keywords -------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("word,stem", [
    ("윤하나가", "윤하나"), ("김민지가", "김민지"), ("목걸이를", "목걸이"), ("주머니에서", "주머니"), ("어머니가", "어머니"),
    ("강아지가", "강아지"), ("스파이를", "스파이"), ("지팡이를", "지팡이"), ("고양이를", "고양이"), ("서도윤이", "서도윤"),
    ("열쇠들을", "열쇠"), ("편지들", "편지"), ("아들을", "아들"), ("서고에서", "서고"), ("민지야", "민지"),
])
def test_v21_stems_take_off_one_ending_and_one_particle(word, stem):
    assert keywords.stems_v21(word)[0] == stem


@pytest.mark.parametrize("query,expected", [
    ("윤하나가 어디 갔지?", ["윤하나", "윤하나가", "갔지"]),
    ("강아지 이름이 뭐였지?", ["강아지", "이름", "이름이"]),  # mid-question: "지" is the word's own
    ("어머니 어디 있어?", ["어머니"]),
    ("스파이 누구였지?", ["스파이"]),  # no 받침 before "이": not a particle
    ("302호에서 12월 25일에 500골드 B2 3층", ["500골드", "302호", "12월", "25일"]),
    ("열쇠들 편지들은 어디 있어?", ["열쇠", "편지", "열쇠들"]),
    ("그는 서고에 들어섰다. 열쇠를 찾아 돌아왔다. 조용히 무거웠다", ["열쇠", "찾아", "서고", "서고에"]),
    ("서고에서 뭐 찾았지?", ["서고", "찾았", "찾았지"]),  # a noun particle came off: a noun, though it ends in 고
])
def test_v21_keywords(query, expected):
    assert keywords.keywords(query, v21=True) == expected
    assert keywords.keywords_v21(query) == expected


def test_v20_keywords_are_unchanged():
    assert keywords.keywords("윤하나가 어디 갔지?") == ["윤하", "갔지", "윤하나", "윤하나가"]
    assert keywords.keywords("302호에서 12월 25일에 500골드 B2 3층") == []
    assert keywords.keywords("그는 서고에 들어섰다. 열쇠를 찾아 돌아왔다. 조용히 무거웠다") == [
        "들어섰다", "돌아왔다", "무거웠다", "조용히"]


def test_v21_particle_lookup_accepts_the_plural():
    _, v20 = keywords.particle_lookup("열쇠")
    _, v21 = keywords.particle_lookup("열쇠", v21=True)
    assert "들을" not in v20 and "(들에게서|" in v21 and v21.endswith(v20[v20.index("에게서|") + len("에게서|"):])
    assert keywords.particle_lookup("열쇠는요", v21=True) is None


# --- gone -----------------------------------------------------------------------------------------------------------

GONE_V21 = [
    "died", "died in battle", "murdered", "executed", "slain", "perished", "passed away", "banished", "found killed",
    "missing, hasn't been found", "exiled to the north", "killed while protecting her brother",
    "missing for three days", "dead due to poison", "was killed by bandits", "has passed away", "위장 출혈로 사망",
    "죽은 상태", "살해됨", "피살", "처형됨", "자살함", "숨짐", "숨을 거둠", "소멸됨", "세상을 떠남", "독살당해 사망함",
    "칼에 찔려 사망함", "화재로 인해 사망", "3년 전 실종됨", "영영 떠남", "전투 중 전사", "사망", "dead",
]
ALIVE_V21 = [
    "reported dead", "reported missing", "사망(위장)", "사망 위장 중", "죽음 위장", "죽음을 위장함", "dead, faked",
    "faked his death", "dead on her feet", "dead in the water", "dead from exhaustion", "dead to the world",
    "missing from class", "missing from work", "떠남", "마을을 떠남", "동생 실종", "아버지 사망", "동생이 살해됨",
    "her brother was killed", "죽은 척", "죽은 동생을 그리워함", "죽은 줄 알았으나 생존", "not dead", "alive",
    "found after going missing", "사망한 것으로 알려짐", "죽은 것으로 보임", "전사", "left arm missing", "죽을 뻔함",
    "살아 있음", "missing piece", "dead end", "위장 잠입 중",
]


@pytest.mark.parametrize("value", GONE_V21)
def test_v21_reads_more_ways_to_be_gone(value):
    assert gone.is_gone_status(value, v21=True)
    assert gone.is_gone_vital(value)


@pytest.mark.parametrize("value", ALIVE_V21)
def test_v21_does_not_silence_a_living_character(value):
    assert not gone.is_gone_status(value, v21=True)
    assert not gone.is_gone_vital(value)


def test_v20_gone_words_are_unchanged():
    assert not gone.is_gone_status("died") and not gone.is_gone_status("살해됨")
    assert gone.is_gone_status("reported dead") and gone.is_gone_status("떠남")
    assert gone.is_gone_status("dead on her feet")  # v20's known false positive, kept for replay
    assert not gone.is_gone_place("저세상") and gone.is_gone_place("저승")
    assert gone.is_gone_place("저세상", v21=True) and gone.is_gone_place("저승", v21=True)
    assert not gone.is_gone_place("the old mill", v21=True)


# --- overuse --------------------------------------------------------------------------------------------------------

def test_exempt_from_rest():
    assert overuse.exempt_from_rest("fact", "addresses") and overuse.exempt_from_rest("fact", "role_toward")
    assert overuse.exempt_from_rest("fact", "feels_toward") and overuse.exempt_from_rest("fact", "relationship")
    assert overuse.exempt_from_rest("thread", None, settled=True)
    assert not overuse.exempt_from_rest("fact", "has_status") and not overuse.exempt_from_rest("excerpt")


def test_rerolls_collapse_and_the_current_turns_attempts_are_left_out(migrated):
    chat = SimChat()
    for i in range(4):
        chat.user(f"Turn {i}.")
        chat.reply(f"Reply {i}.")
    chat.user("Now?")
    with make_client(migrated) as client:
        sync(client, chat)
    with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
        conv = conn.execute("SELECT id, head_commit_id FROM conversation WHERE host_chat_ref = %s",
                            (chat.id,)).fetchone()
        t0 = datetime.now(timezone.utc) - timedelta(hours=1)

        def trace(at: int, position: int, key: str) -> None:
            line = {"kind": "fact", "ref": {"assertion": key}, "placed": True, "content": "a line nobody echoes"}
            conn.execute(
                "INSERT INTO retrieval_trace (id, conversation_id, query, candidates, selected, excluded_in_context,"
                " token_estimate, latency_ms, freshness, created_at, upto_position, lines)"
                " VALUES (%s, %s, 'q', '[]', '[]', '[]', 0, '{}', 'fresh', %s, %s, %s)",
                (uuid4(), conv["id"], t0 + timedelta(minutes=at), position, Jsonb([line])))

        def placed(**kw):
            return [sorted(k for _, k in r.placed) for r in overuse.recent(conn, conv["id"], conv["head_commit_id"],
                                                                           n=3, **kw)]

        trace(0, 2, "a")
        trace(1, 4, "b")
        trace(2, 6, "c")
        first = placed(dedupe_positions=True, exclude_position=8)  # attempt 1 of the request at position 8
        assert first == [["c"], ["b"], ["a"]] == placed()
        trace(3, 8, "d1")  # attempt 1 recorded, then two rerolls at the same position
        trace(4, 8, "d2")
        trace(5, 8, "d3")
        assert placed() == [["d3"], ["d2"], ["d1"]]  # v20: the rerolls fill the window
        assert placed(dedupe_positions=True) == [["d3"], ["c"], ["b"]]  # one request per position
        assert placed(dedupe_positions=True, exclude_position=8) == first  # attempt 4 rests what attempt 1 rested
        many = [overuse.Recent(frozenset({("fact", "x")}), frozenset())] * 3
        assert overuse.tired(many)  # sanity: the window the collapse keeps full is what rest reads
        for i in range(40):  # more rerolls than a page: still collapsed
            trace(6 + i, 10, f"e{i}")
        assert placed(dedupe_positions=True) == [["e39"], ["d3"], ["c"]]
        assert placed(dedupe_positions=True, exclude_position=10) == [["d3"], ["c"], ["b"]]


# --- memory map -----------------------------------------------------------------------------------------------------

def test_told_chains_link_a_retelling_in_other_words():
    rows = [told_row("세라", "카이토", "왕이 독살당했다", turn=3), told_row("카이토", "하나", "왕이 독살당했대", turn=5)]
    chains = memorymap.told_chains(rows)
    assert [[(link["teller"], link["hearer"]) for link in c] for c in chains] == [[("세라", "카이토"), ("카이토", "하나")]]
    assert chains[0][1]["what"] == "왕이 독살당했대"


def test_told_chains_keep_every_branch_as_its_own_path():
    rows = [told_row("세라", "카이토", "the key is under the mat", turn=1),
            told_row("카이토", "하나", "the key is under the mat", turn=2),
            told_row("카이토", "유나", "the key is under the mat", turn=3),
            told_row("하나", "세라", "the key is under the mat", turn=4)]
    chains = memorymap.told_chains(rows)
    assert [[link["hearer"] for link in c] for c in chains] == [["카이토", "하나", "세라"], ["카이토", "유나"]]
    assert all(set(link) == {"teller", "hearer", "what", "about", "turn"} for c in chains for link in c)


def test_told_chains_do_not_join_different_rumours_through_the_same_people():
    rows = [told_row("세라", "카이토", "비밀", turn=1), told_row("카이토", "하나", "비밀번호는 1234", turn=2),
            told_row("세라", "카이토", "the mill burned", turn=3), told_row("카이토", "하나", "the king is ill", turn=4)]
    chains = memorymap.told_chains(rows)
    assert [len(c) for c in chains] == [1, 1, 1, 1]
    assert memorymap.told_similarity("비밀", "비밀번호는 1234") < memorymap.TOLD_SIMILAR


def test_events_carry_when_it_happened_and_its_knowledge_marks_only_when_present():
    secret = fact(HANA, "event", value="hid the letter", history=[step(4, "hid the letter")],
                  when_happened="three years ago", knowledge="limited", known_by=["Hana"], hidden_from=["Kaito"])
    plain = fact(KAITO, "event", value="arrives", history=[step(2, "arrives")])
    evs = memorymap.events(view([secret, plain]))
    assert evs[1]["when_happened"] == "three years ago" and evs[1]["knowledge"] == "limited"
    assert evs[1]["known_by"] == ["Hana"] and evs[1]["hidden_from"] == ["Kaito"]
    assert not {"when_happened", "knowledge", "known_by", "hidden_from"} & set(evs[0])


def test_graph_leaves_out_an_excluded_group_or_place():
    facts = [fact(HANA, "member_of", GUILD, otype="group", history=[step(3, None, "the guild")]),
             fact(KAITO, "located_in", MILL, otype="place", history=[step(3, None, "the old mill")])]
    g = memorymap.graph(view(facts, excluded={GUILD: {"scope": "cast"}, MILL: {"scope": "cast"}}))
    ids = {n["id"] for n in g["nodes"]}
    assert GUILD not in ids and MILL not in ids and g["edges"] == []
    assert HANA not in ids and KAITO not in ids  # no orphan character left by the dropped tie
    kept = memorymap.graph(view(facts))
    assert {GUILD, MILL, HANA, KAITO} <= {n["id"] for n in kept["nodes"]}
    assert entity(GUILD, "group")["type"] == "group"
