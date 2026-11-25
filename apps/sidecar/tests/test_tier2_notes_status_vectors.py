"""Tier 2/4: the author's note in the chat's language with a secret check across scripts, its open threads capped and
checked, the first turns' chronicle (notes); status windows of several characters, lines, brackets, tables and HTML
cards (statusshape, parsers); opt-in chunk overlap (vectors). No database: pure functions only."""

from __future__ import annotations

import pytest

from nmos_sidecar import notes, parsers, statusshape
from nmos_sidecar.llm import LLMError
from nmos_sidecar.vectors import CHUNK_CHARS, CHUNK_OVERLAP, MAX_CHUNKS, chunks

# --- notes: shared stand-ins --------------------------------------------------------------------------------------------


class Writer:
    """A stand-in model: its replies in order, the prompts it saw."""

    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def __call__(self, system, user):
        self.calls.append((system, user))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply, "{}"


def scene(first, last, text, told=("밀수꾼이다", "smuggler")):
    return {"window": None, "summary": {"id": f"s{first}", "first_turn": first, "last_turn": last, "text": text,
                                        "coverage": {"secrets": list(told)}}}


def told(*scenes, story=None):
    return {"scenes": list(scenes), "story": story}


def thread(text, turn, status="open", kind="promise", by="하나", to="도윤", **kw):
    return {"kind": kind, "by": by, "to": to, "text": text, "turn": turn, "status": status,
            "closed_by": {"turn": turn + 2} if status != "open" else None, "knowledge": None, "hidden_from": None,
            **kw}


def fact(subject, predicate, *, obj=None, value=None, turn=5, **kw):
    return {"subject": subject, "predicate": predicate, "object": obj, "value": value, "turn": turn, "position": turn,
            "polarity": "positive", "history": [], "knowledge": None, "hidden_from": None, "claims": [], **kw}


KO_SECRET = {"open": ["도윤"], "holders": ["하나"], "text": "하나 identity: 밀수꾼이다", "turn": 2, "position": 2}
EN_SECRET = {"open": ["Kaito"], "holders": ["Hana"], "text": "Hana identity: smuggler", "turn": 2, "position": 2}
KO_SCENE = scene(0, 7, "하나가 방앗간에 갔다. 도윤은 등대에서 기다렸다.")


@pytest.fixture(autouse=True)
def _fresh_cache():
    notes.clear_cache()
    yield
    notes.clear_cache()


# --- notes: the language a model writes in ------------------------------------------------------------------------------

def test_a_korean_chat_gets_a_korean_chronicle_by_default_and_english_on_request():
    w = Writer({"events": "- 하나가 방앗간에 갔다 (t0–7).", "now": ""}, {"events": "- Hana went to the mill.", "now": ""})
    ko = notes.chronicle(told(KO_SCENE), [], [], [], 3000, model=w)
    en = notes.chronicle(told(KO_SCENE), [], [], [], 3000, model=w, language="en")
    assert "Write two parts in Korean, the language of the chat;" in w.calls[0][0]
    # English is the prompt as it was before `language` existed, word for word
    assert "Write two parts in English, whatever the language of the chat; keep names" in w.calls[1][0]
    assert ko["made"] == en["made"] == "model" and len(w.calls) == 2  # the language is part of the cache key
    assert "하나가 방앗간에 갔다" in ko["body"] and "Hana went to the mill." in en["body"]


def test_an_english_chat_stays_english_by_default():
    w = Writer({"events": "- e", "now": ""})
    notes.chronicle(told(scene(0, 7, "Hana walked to the mill.")), [], [], [], 3000, model=w)
    assert "in English, whatever the language of the chat" in w.calls[0][0]


def test_the_language_is_read_from_the_scene_summaries_then_threads_and_facts():
    assert notes.chat_language([{"text": "하나가 웃었다."}], None, [thread("meet at the lighthouse", 3)], []) == "ko"
    assert notes.chat_language([{"text": "Hana laughed at 하나's joke."}], None, [], []) == "en"
    assert notes.chat_language([], None, [thread("등대에서 만나기", 3)], []) == "ko"
    assert notes.chat_language([], None, [], [fact("Hana", "located_in", obj="the mill")]) == "en"
    assert notes.script("") == "en"
    with pytest.raises(ValueError):
        notes.language_of("ja", [], None, [], [])


def test_the_custom_part_writes_in_the_chats_language_unless_asked_for_english():
    w = Writer({"text": "- 하나: 회색 코트"}, {"text": "- Hana: a grey coat"})
    notes.custom("의상을 정리해줘.", told(KO_SCENE), [], [], [], 3000, model=w)
    notes.custom("의상을 정리해줘.", told(KO_SCENE), [], [], [], 3000, model=w, language="en")
    assert "Write in Korean, the language of the chat, unless the instruction" in w.calls[0][0]
    assert "Write in English, unless the instruction explicitly names another" in w.calls[1][0]


def test_ask_takes_a_language_and_make_passes_it_on():
    assert notes.Ask.of({"sections": ["chronicle"]}).language == "chat"
    assert notes.Ask.of({"sections": ["chronicle"], "language": "en"}).language == "en"
    with pytest.raises(ValueError):
        notes.Ask.of({"sections": ["chronicle"], "language": "ko"})
    view = {"facts": [], "threads": [], "secrets": []}
    w = Writer({"events": "- e", "now": ""})
    notes.make(notes.Ask.of({"sections": ["chronicle"], "language": "en"}), view, told(KO_SCENE), 7, w, "2026-11-25")
    assert "in English, whatever" in w.calls[0][0]


# --- notes: secrets across scripts --------------------------------------------------------------------------------------

def test_a_korean_chronicle_of_a_korean_secret_is_checked_by_its_letters():
    bad = {"events": "- 하나는 사실 밀수꾼이다.", "now": ""}
    w = Writer(bad, bad)
    out = notes.chronicle(told(KO_SCENE), [], [], [KO_SECRET], 3000, model=w)
    assert len(w.calls) == 2 and "YOUR LAST ANSWER TOLD" in w.calls[1][1]
    assert out["made"] == "assembled" and "밀수꾼" not in out["body"]


def test_an_english_reply_of_a_korean_secret_goes_to_the_semantic_check():
    asked = []

    def semantic(text, secrets):
        asked.append((text, [s["text"] for s in secrets]))
        return [s for s in secrets if "smuggl" in text]

    w = Writer({"events": "- Hana is secretly a smuggler.", "now": ""}, {"events": "- Hana went to the mill.", "now": ""})
    out = notes.chronicle(told(KO_SCENE), [], [], [KO_SECRET], 3000, model=w, language="en", semantic_leaks=semantic)
    assert len(w.calls) == 2 and "밀수꾼이다" in w.calls[1][1]  # asked again without it
    assert out["made"] == "model" and "smuggler" not in out["body"]
    assert all(secrets == [KO_SECRET["text"]] for _, secrets in asked)


def test_without_a_semantic_check_the_cross_script_reply_is_not_caught_which_is_why_chat_is_the_default():
    w = Writer({"events": "- Hana is secretly a smuggler.", "now": ""})
    out = notes.chronicle(told(KO_SCENE), [], [], [KO_SECRET], 3000, model=w, language="en")
    assert out["made"] == "model"  # summaries.leaks compares letters: documented gap, closed by semantic_leaks


def test_the_semantic_check_skips_secrets_in_the_replys_own_script():
    calls = []
    w = Writer({"events": "- Hana walked.", "now": ""})
    notes.chronicle(told(scene(0, 7, "Hana walked.")), [], [], [EN_SECRET], 3000, model=w,
                    semantic_leaks=lambda text, secrets: calls.append(secrets) or [])
    assert calls == []


def test_a_semantic_check_that_fails_counts_as_told():
    def broken(text, secrets):
        raise LLMError("embedder down")

    w = Writer({"events": "- Hana went to the mill.", "now": ""}, {"events": "- Hana went home.", "now": ""})
    out = notes.chronicle(told(KO_SCENE), [], [], [KO_SECRET], 3000, model=w, language="en", semantic_leaks=broken)
    assert len(w.calls) == 2 and out["made"] == "assembled"
    c = notes.custom("Who?", told(KO_SCENE), [], [], [KO_SECRET], 3000, model=Writer({"text": "- x"}, {"text": "- y"}),
                     language="en", semantic_leaks=broken)
    assert c["reason"] == "held" and c["body"] == ""


def test_with_secrets_told_nothing_is_checked():
    calls = []
    w = Writer({"events": "- Hana is a smuggler (secret: 도윤 does not know).", "now": ""})
    out = notes.chronicle(told(KO_SCENE), [], [], [KO_SECRET], 3000, model=w, told_secrets=True, language="en",
                          semantic_leaks=lambda t, s: calls.append(s) or s)
    assert out["made"] == "model" and calls == []


def test_embedding_leak_checker_finds_a_sentence_near_a_secret():
    class Embedder:
        def __init__(self):
            self.calls = []

        def embed(self, texts, timeout_s):
            self.calls.append(texts)
            return [[1.0, 0.0] if ("밀수" in t or "smuggl" in t) else [0.0, 1.0] for t in texts]

    e = Embedder()
    check = notes.embedding_leak_checker(e)
    assert check("Hana went to the mill. She is a smuggler at night.", [KO_SECRET]) == [KO_SECRET]
    assert check("Hana went to the mill.", [KO_SECRET]) == []
    assert check("", [KO_SECRET]) == [] and len(e.calls) == 2  # nothing to embed: no request
    assert e.calls[0][0] == "identity: 밀수꾼이다" or "밀수꾼이다" in e.calls[0][0]


def test_model_leak_checker_reads_the_numbers_and_refuses_anything_else():
    check = notes.model_leak_checker(Writer({"told": [1, 1, 5]}, {"told": "yes"}))
    assert check("Hana is a smuggler.", [KO_SECRET, EN_SECRET]) == [KO_SECRET]
    with pytest.raises(LLMError):
        check("Hana is a smuggler.", [KO_SECRET])
    assert notes.model_leak_checker(Writer())("  ", [KO_SECRET]) == []


# --- notes: the open threads and the assembled lines --------------------------------------------------------------------

def test_an_open_thread_or_an_assembled_line_that_tells_a_secret_is_left_out():
    threads = [thread("등대에서 만나기", 3), thread("밀수꾼이다 들키지 않기", 4),
               thread("밀수꾼이다 숨기기", 1, status="achieved", kind="goal")]
    now = [fact("하나", "has_status", value="밀수꾼이다", turn=6), fact("하나", "located_in", obj="방앗간", turn=6)]
    out = notes.chronicle(told(KO_SCENE), threads, now, [KO_SECRET], 3000, model=None)
    assert out["made"] == "assembled" and "밀수꾼" not in out["body"]
    assert "등대에서 만나기" in out["body"] and "방앗간" in out["body"] and "more open threads" not in out["body"]


def test_open_threads_are_capped_so_the_story_keeps_its_room():
    many = [thread(f"약속 {i}번을 지키기", i) for i in range(40)]
    out = notes.chronicle(told(KO_SCENE), many, [], [], 3000, model=None)
    tail = out["body"].split("## Open threads\n", 1)[1]
    lines = tail.splitlines()
    assert lines[-1] == "- (+25 more open threads)" and len(lines) == 16
    assert "약속 39번" in tail and "약속 24번" not in tail  # the newest kept, in the store's order
    long = [thread("아주 긴 약속 " + "가" * 300 + f" {i}", i) for i in range(10)]
    capped = notes.chronicle(told(KO_SCENE), long, [], [], 3000, model=None)["body"].split("## Open threads\n", 1)[1]
    assert len(capped) <= 3000 * notes.THREADS_SHARE + 60 and capped.endswith("more open threads)")


def test_the_model_gets_room_left_by_the_capped_threads():
    w = Writer({"events": "- e", "now": ""})
    notes.chronicle(told(KO_SCENE), [thread("가" * 200 + f" {i}", i) for i in range(60)], [], [], 3000, model=w)
    budget = int(w.calls[0][0].split("Together at most ")[1].split()[0])
    assert budget >= 3000 * (1 - notes.THREADS_SHARE) - 100


# --- notes: the first turns ---------------------------------------------------------------------------------------------

def test_before_the_first_scene_summary_the_chronicle_tells_the_threads_and_now():
    threads = [thread("등대에서 만나기", 3), thread("종 찾기", 1, status="achieved", kind="goal")]
    now = [fact("하나", "located_in", obj="방앗간", turn=4)]
    out = notes.chronicle(told(), threads, now, [], 3000, model=None, last_turn=9)
    assert out["reason"] == "" and out["made"] == "assembled" and out["turns"] == "1-9"
    assert out["body"].startswith("## Chronicle (t1–9)\n- 하나 → 도윤: 종 찾기 → achieved (t3)\n\n## Now\n- 하나 — location: 방앗간")
    assert out["body"].endswith("## Open threads\n- 하나 → 도윤: 등대에서 만나기 (promise, since t3)")
    w = Writer({"events": "- 하나가 종을 찾았다 (t1–3).", "now": "- 하나는 방앗간에 있다."})
    made = notes.chronicle(told(), threads, now, [], 3000, model=w, last_turn=9)
    assert made["made"] == "model" and "SCENES: (none to read" in w.calls[0][1] and "in Korean" in w.calls[0][0]
    only_open = notes.chronicle(told(), threads[:1], [], [], 3000, model=None, last_turn=None)
    assert only_open["body"] == "## Chronicle (t3–3)\n\n## Open threads\n- 하나 → 도윤: 등대에서 만나기 (promise, since t3)"


def test_the_custom_part_is_made_in_the_first_turns_too():
    w = Writer({"text": "- 하나: 방앗간"})
    out = notes.custom("위치를 정리해줘.", told(), [], [fact("하나", "located_in", obj="방앗간", turn=4)], [], 3000,
                       model=w, last_turn=5)
    assert out["made"] == "model" and out["turns"] == "4-5" and "SCENES: (none to read" in w.calls[0][1]
    assert notes.custom("x", told(), [], [fact("하나", "relationship", obj="도윤", value="친구")], [], 3000,
                        model=Writer())["reason"] == "no_scenes"


def test_without_a_summarizer_the_chronicle_is_made_from_threads_too():
    """`told` is None when no summarizer is active, and `newest` is empty when every summary is held: the same path as
    the first turns, now a chronicle of the threads and NOW facts rather than `no_scenes`."""
    out = notes.chronicle(None, [thread("등대에서 만나기", 290)], [], [], 3000, model=None, last_turn=300)
    assert out["made"] == "assembled" and out["turns"] == "290-300" and "등대에서 만나기" in out["body"]
    held = notes.chronicle(told(scene(0, 7, "하나는 밀수꾼이다.")), [thread("등대에서 만나기", 3)], [], [KO_SECRET],
                           3000, model=None, last_turn=8)
    assert held["held"] == 1 and "밀수꾼" not in held["body"] and "등대에서 만나기" in held["body"]


def test_a_chronicle_whose_every_line_tells_a_secret_says_nothing():
    out = notes.chronicle(told(), [thread("밀수꾼이다 들키지 않기", 2)], [], [KO_SECRET], 3000, model=None)
    assert out["body"] == "" and out["made"] == "none" and out["reason"] == "none"
    view = {"facts": [], "threads": [thread("밀수꾼이다 들키지 않기", 2)], "secrets": [KO_SECRET]}
    assert notes.make(notes.Ask.of({"sections": ["chronicle"]}), view, told(), 3, None, "2026-11-25")["text"] == ""


# --- status windows ---------------------------------------------------------------------------------------------------

CARD = "Tier2 card"


def shape(*keys):
    return parsers.compile_rules({"rules": [{"card": CARD, "id": "s", "kind": "shape", "keys": list(keys)}]})


def read(rules, text):
    return {k: v for _, k, v in parsers.parse(rules, text, "char", None, CARD)}


def found(text):
    return [(b.entity, dict(b.fields)) for b in statusshape.blocks(text)]


def test_three_characters_windows_keep_their_own_keys():
    text = ("[서연 | HP: 80 | MP: 30 | 호감도: 45]\n[도윤 | HP: 120 | MP: 10 | 호감도: 20]\n"
            "【하나 상태창】\nHP: 50\nMP: 70\n호감도: 90")
    assert read(shape("HP", "MP", "호감도"), text) == {
        "서연.HP": "80", "서연.MP": "30", "서연.호감도": "45", "도윤.HP": "120", "도윤.MP": "10", "도윤.호감도": "20",
        "하나.HP": "50", "하나.MP": "70", "하나.호감도": "90"}
    assert {b.keys for b in statusshape.blocks(text)} == {frozenset({"HP", "MP", "호감도"})}  # keys stay bare


def test_one_characters_window_keeps_bare_keys_and_two_characters_are_prefixed():
    """Owner 2026-11-25: a prefix only when one reply holds two characters' windows; one character keeps its keys."""
    rules = shape("HP", "MP", "호감도")
    assert read(rules, "[서연 | HP: 80 | MP: 30 | 호감도: 45]") == {"HP": "80", "MP": "30", "호감도": "45"}
    assert read(rules, "[서연 | HP: 1 | MP: 2 | 호감도: 3]\n[서연 | HP: 4 | MP: 5 | 호감도: 6]") == {
        "HP": "4", "MP": "5", "호감도": "6"}  # the same name twice is one character
    together = read(rules, "[서연 | HP: 70 | MP: 30 | 호감도: 46]\n[도윤 | HP: 1 | MP: 2 | 호감도: 3]")
    assert together["서연.HP"] == "70" and together["도윤.HP"] == "1" and "HP" not in together


@pytest.mark.parametrize("text", [
    "[Status | HP: 1 | MP: 2 | 위치: 집]", "[INFO | a=1 | b=2 | c=3]", "[ 🎮 | Date: 3월 2일 | Time: 밤 | Location: 집 ]",
    "[Day 3 | HP: 1 | MP: 2 | 위치: 집]", "[상태창]\nHP: 1\nMP: 2\n위치: 집",
])
def test_a_label_names_no_character(text):
    [(entity, _)] = found(text)
    assert entity is None


def test_a_place_or_a_scene_word_is_never_a_character():
    rules = shape("날짜", "시간", "날씨")
    assert read(rules, "[교실 | 날짜: 3일 | 시간: 오후 | 날씨: 맑음]") == {"날짜": "3일", "시간": "오후", "날씨": "맑음"}
    # two places in one reply: every key is the scene's, so nothing is prefixed
    two = read(rules, "[교실 | 날짜: 3일 | 시간: 오후 | 날씨: 맑음]\n[복도 | 날짜: 3일 | 시간: 밤 | 날씨: 비]")
    assert set(two) == {"날짜", "시간", "날씨"}
    # two characters with a scene key: the scene key stays bare, the rest is each character's
    mixed = read(shape("위치", "HP", "MP"), "[서연 | 위치: 숲 | HP: 1 | MP: 2]\n[도윤 | 위치: 숲 | HP: 3 | MP: 4]")
    assert mixed == {"위치": "숲", "서연.HP": "1", "서연.MP": "2", "도윤.HP": "3", "도윤.MP": "4"}


def test_entity_names_from_labels():
    assert statusshape.entity_of("서연 상태창") == "서연"
    assert statusshape.entity_of("서연의 상태창") == "서연"
    assert statusshape.entity_of("Seoyeon's Status") == "Seoyeon"
    assert statusshape.entity_of("HUD") is None and statusshape.entity_of("상태") is None


def test_a_pipe_inside_a_nested_bracket_and_a_short_bare_segment_continue_a_field():
    assert found("【HP: 80 | 소지품: [물약 x2 | 열쇠 x1] | 상태: 중독 | 출혈 | 위치: 숲】") == [
        (None, {"HP": "80", "소지품": "[물약 x2 | 열쇠 x1]", "상태": "중독 | 출혈", "위치": "숲"})]
    assert found("『HP: 1 | MP: 2 | 위치: 집』") == [(None, {"HP": "1", "MP": "2", "위치": "집"})]
    assert found("《HP: 1 | MP: 2 | 위치: 집》") == [(None, {"HP": "1", "MP": "2", "위치": "집"})]


def test_windows_over_several_lines():
    assert found("[서연 상태창]\n날짜: 3일\n위치: 숲\nHP: 80\n\n그리고 걸었다.") == [
        ("서연", {"날짜": "3일", "위치": "숲", "HP": "80"})]
    assert found("상태창:\n- HP: 80\n- MP: 40\n- 위치: 집") == [(None, {"HP": "80", "MP": "40", "위치": "집"})]
    assert found("[\n도윤\nHP: 1\nMP: 2\n위치: 3\n]") == [("도윤", {"HP": "1", "MP": "2", "위치": "3"})]
    assert found("```\nHP: 1\nMP: 2\n위치: 3\n```") == [(None, {"HP": "1", "MP": "2", "위치": "3"})]
    assert found("| 항목 | 값 |\n|---|---|\n| HP | 80 |\n| MP | 40 |\n| 위치 | 집 |") == [
        (None, {"HP": "80", "MP": "40", "위치": "집"})]


def test_html_status_cards_are_read_as_their_text_and_placed_in_the_message():
    card = ('앞 문장.<style>.st{color:red}\n.hp{width:80%}</style><div class="st">\n  <div>HP: 80</div>\n'
            '  <div>MP: 40</div>\n  <div>위치: 집</div>\n</div>뒤 문장.')
    [b] = statusshape.blocks(card)
    assert dict(b.fields) == {"HP": "80", "MP": "40", "위치": "집"} and ".st" not in str(b.fields)
    assert card[b.start:b.end].startswith("HP: 80") and card[b.start:b.end].endswith("<div>위치: 집")
    table = ("<table>\n <tr>\n  <td>HP</td>\n  <td>80</td>\n </tr>\n <tr><td>MP</td> <td>40</td></tr>\n"
             " <tr><td>위치</td><td>집</td></tr>\n</table>")
    assert found(table) == [(None, {"HP": "80", "MP": "40", "위치": "집"})]
    assert found("<h3>서연 상태창</h3><p>HP: 80</p><p>MP: 40</p><p>위치: 집</p>") == [
        ("서연", {"HP": "80", "MP": "40", "위치": "집"})]
    rules = shape("HP", "MP", "위치")
    assert read(rules, card) == {"HP": "80", "MP": "40", "위치": "집"}
    assert parsers.prose(rules, card, "char", None, CARD).startswith("앞 문장.<style>")
    assert "HP" not in parsers.prose(rules, card, "char", None, CARD) and "뒤 문장." in parsers.prose(
        rules, card, "char", None, CARD)


@pytest.mark.parametrize("text", [
    "하나: 안녕.\n도윤: 응?\n하나: 가자!",  # a script's dialogue
    "[대화]\n하나: 안녕.\n도윤: 응?\n하나: 가자!",
    "<p>하나: 안녕.</p><p>도윤: 응?</p><p>하나: 가자!</p>",
    "HP: 80\nMP: 40\n위치: 집",  # field lines without a header
    "그는 『오늘은 | 이상하게도 | 길다』 라고 썼다.",
    "『그는 오래 말했다.\n하나: 그래\n도윤: 응\n하나: 가자』",
    "| 이름 | 나이 | 직업 |\n|---|---|---|\n| 하나 | 17 | 학생 |",
    "[LBDATA START]\nauthor=하나|time=얼마 전|content=소문\n[LBDATA END]",
])
def test_prose_dialogue_and_other_shapes_are_no_window(text):
    assert statusshape.blocks(text) == []


def test_an_unclosed_quotation_hides_no_window():
    assert found("『그는 말했다 [HP: 1 | MP: 2 | 위치: 집]") == [(None, {"HP": "1", "MP": "2", "위치": "집"})]


# --- parsers: HTML in values and blocks -----------------------------------------------------------------------------------

def test_clean_keeps_block_boundaries_and_drops_styles():
    assert parsers._clean("<div>HP: 80</div><div>MP: 40</div>") == "HP: 80 MP: 40"
    assert parsers._clean("a<br>b") == "a b" and parsers._clean("<b>물약</b> x2") == "물약 x2"
    assert parsers._clean("<style>.st{color:red}</style>80") == "80"
    assert parsers._clean("<td>중독</td><td>출혈</td>") == "중독 | 출혈"
    assert parsers._clean("HP < 50") == "HP < 50" and parsers._clean("  plain  ") == "plain"
    assert parsers.markup("<p>a</p><p>b</p>") == "\na\nb\n" and parsers.markup("no tags\n x") == "no tags\n x"


def test_a_block_rule_reads_an_html_card_line_by_line():
    rules = parsers.compile_rules({"rules": [{"card": CARD, "id": "b", "kind": "block", "start": r"\[STATUS\]",
                                              "end": r"\[/STATUS\]"}]})
    text = "[STATUS]<style>\n.st{color:red}\n</style><div>HP: 80</div><div>MP: 40</div>[/STATUS]"
    assert read(rules, text) == {"HP": "80", "MP": "40"}


def test_arrows_in_a_block_are_no_tag():
    rules = parsers.compile_rules({"rules": [{"card": CARD, "id": "b", "kind": "block", "start": r"\[STATUS\]",
                                              "end": r"\[/STATUS\]"}]})
    assert read(rules, "[STATUS]\nHP: 10 <- 20\nMP: 30\n위치: 집 -> 학교\n[/STATUS]") == {
        "HP": "10 <- 20", "MP": "30", "위치": "집 -> 학교"}
    assert found("[상태창]\nHP: 10 <- 20\nMP: 30\n위치: 집 -> 학교") == [
        (None, {"HP": "10 <- 20", "MP": "30", "위치": "집 -> 학교"})]


def test_a_block_rule_with_a_tag_as_its_separator_still_splits_on_it():
    rules = parsers.compile_rules({"rules": [{"card": CARD, "id": "b", "kind": "block", "start": r"\[S\]",
                                              "end": r"\[/S\]", "separator": "<br>"}]})
    assert read(rules, "[S]HP: 1<br>MP: <b>2</b><br>위치: 집[/S]") == {"HP": "1", "MP": "2", "위치": "집"}


def test_a_regex_value_does_not_glue_two_blocks():
    rules = parsers.compile_rules({"rules": [{"card": CARD, "id": "r", "kind": "regex",
                                              "pattern": r"상태: (?P<value>.+)", "key": "상태"}]})
    assert read(rules, "상태: <div>중독</div><div>출혈</div>") == {"상태": "중독 출혈"}


# --- vectors: opt-in overlap --------------------------------------------------------------------------------------------

TEXTS = ["", "   ", "가나다. " * 300, "word " * 400, "x" * 2000, "Hana hid the key. " * 90, "a\n" * 900]


@pytest.mark.parametrize("text", TEXTS)
def test_no_overlap_cuts_as_chunk_v1(text):
    assert chunks(text) == chunks(text, CHUNK_CHARS, MAX_CHUNKS, 0) == chunks(text, overlap=0)


@pytest.mark.parametrize("text", TEXTS)
@pytest.mark.parametrize("size,overlap", [(700, CHUNK_OVERLAP), (50, 10), (10, 3), (10, 999), (700, -5)])
def test_overlapping_chunks_always_move_forward(text, size, overlap):
    spans = chunks(text, size, MAX_CHUNKS, overlap)
    assert len(spans) <= MAX_CHUNKS and all(0 <= a < b <= len(text) and b - a <= size for a, b in spans)
    assert all(spans[i][0] < spans[i + 1][0] and spans[i][1] < spans[i + 1][1] for i in range(len(spans) - 1))
    assert all(spans[i][0] <= spans[i + 1][0] - 0 and spans[i + 1][0] >= spans[i][1] - max(0, min(overlap, size // 2))
               for i in range(len(spans) - 1))


def test_overlap_starts_at_a_word_and_ends_at_the_text():
    text = "word " * 150  # 750 characters: two chunks, no third tail chunk
    spans = chunks(text, 700, MAX_CHUNKS, CHUNK_OVERLAP)
    assert len(spans) == 2 and spans[-1][1] == len(text)
    assert spans[1][0] < spans[0][1] and text[spans[1][0] - 1] == " "


def test_a_fact_across_a_cut_is_whole_in_one_chunk_with_overlap():
    fact_text = "the silver key is under the lighthouse stairs"
    text = "filler " * 95 + fact_text + " filler" * 60  # no sentence end near the cut: it falls at 700, in the fact
    at = text.index(fact_text)
    whole = lambda spans: any(a <= at and at + len(fact_text) <= b for a, b in spans)  # noqa: E731
    assert not whole(chunks(text, 700))  # chunk-v1 cuts through it
    assert whole(chunks(text, 700, MAX_CHUNKS, CHUNK_OVERLAP))
