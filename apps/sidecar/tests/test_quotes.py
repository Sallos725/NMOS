"""PHASE-33 Q1–Q3 (ADR 0067): the quote route's cue, words, lines and choice. Pure; synthetic text."""

from nmos_sidecar import quotes
from nmos_sidecar.quotes import QUOTE_CHARS, asks_for_words, named, named_turn, pick, query_terms, quotes_in

NAMES = {"한솔": "한솔", "류진": "류진", "백도": "백도"}


def _msg(n, text, turn=None, role="assistant", name="narrator", position=None):
    return {"id": f"r{n}", "clean": text, "turn": n if turn is None else turn, "position": n if position is None else position,
            "role": role, "name": name}


def test_a_question_about_words_is_the_cue():
    assert asks_for_words("한솔이 그때 뭐라고 했지?")
    assert asks_for_words('누가 "등불"이라고 말했어?')
    assert asks_for_words("What did Ryu say at the dock?")
    assert not asks_for_words("한솔은 지금 어디 있어?")
    assert not asks_for_words("류진은 한솔을 뭐라고 부르지?")  # the form of address now: the facts hold it
    assert asks_for_words("류진은 처음에 한솔을 뭐라고 불렀더라?")  # the older forms are the answer
    assert named_turn("12턴에 류진이 뭐라고 했어?") == 12
    assert named_turn("what was said on turn 7") == 7
    assert named_turn("류진이 뭐라고 했어?") is None


def test_the_words_of_a_question_leave_out_cues_and_weigh_verbs_half():
    terms = query_terms("처음 만났을 때 한솔이 등대에 대해 뭐라고 중얼거렸지?")
    assert "처음" not in terms and "대해" not in terms and "뭐라고" not in terms and "중얼거렸지" not in terms
    assert terms["등대"] == 1.0 and terms["한솔"] == 1.0
    assert terms["만났"] == quotes.VERB_WEIGHT


def test_the_subject_of_the_question_is_the_speaker_and_the_others_are_words():
    assert named("류진이 한솔한테 뭐라고 했어?", NAMES) == ({"류진"}, {"한솔"})
    assert named("류진이랑 한솔 중 누가 그 말 했지?", NAMES) == ({"류진", "한솔"}, set())


def test_a_line_grows_both_ways_from_its_quote_within_the_cap():
    before = " ".join(f"앞 문장 {n}번이다." for n in range(30))
    after = " ".join(f"뒤 문장 {n}번이다." for n in range(30))
    text = f'{before} "닻은 내일 올린다." 류진이 고개를 들었다. {after}'
    [spoken] = quotes_in(text)
    assert spoken.words == "닻은 내일 올린다."
    assert len(spoken.line) <= QUOTE_CHARS
    assert spoken.line.index("닻은") > 100 and len(spoken.line) - spoken.line.index("닻은") > 100  # not cut at the quote
    assert "류진" in spoken.after


def test_rare_words_decide_between_two_lines():
    chat = [_msg(1, '한솔이 웃었다. "바다가 좋네." 바다 바람이 불었다.'),
            _msg(2, '한솔이 등불을 들었다. "이건 꺼지면 안 돼." 바다 쪽으로 걸었다.')]
    plain = pick(chat, "한솔이 바다에서 등불 들고 뭐라고 했어?", NAMES, 10, False)
    weighted = pick(chat, "한솔이 바다에서 등불 들고 뭐라고 했어?", NAMES, 10, False, rarity={"바다": 0.1, "등불": 1.0})
    assert weighted[0].words == "이건 꺼지면 안 돼."
    assert {q.words for q in plain} == {"바다가 좋네.", "이건 꺼지면 안 돼."}


def test_a_named_turn_leads():
    chat = [_msg(3, '"그물은 내가 걷지." 류진이 말했다.'), _msg(9, '"그물은 네가 걷어라." 류진이 말했다.')]
    [top, *_] = pick(chat, "9턴에 류진이 그물 얘기하면서 뭐라고 했지?", NAMES, 10, False)
    assert top.turn == 9 and top.speaker == "류진"


def test_a_first_cue_reads_where_everyone_named_had_appeared():
    chat = [_msg(1, '백도가 말했다. "어서 와라, 류진아."'), _msg(6, '한솔이 말했다. "처음 뵙겠습니다, 류진 씨."'),
            _msg(20, '한솔이 말했다. "류진 씨, 오늘도 늦었네요."')]
    [top, *_] = pick(chat, "한솔이 류진을 처음 만났을 때 뭐라고 했어?", NAMES, 30, True, met=6)
    assert top.turn == 6


def test_the_second_line_comes_from_another_exchange():
    filler = " ".join(f"물결이 {n}번 밀려왔다." for n in range(150))
    text = f'"그물이 무겁다." 류진이 그물을 걷었다. {filler} "그물은 내가 말린다." 한솔이 그물을 받았다.'
    close = '"그물 하나." 백도가 셌다. "그물 둘." 백도가 마저 셌다.'
    picked = pick([_msg(4, close), _msg(8, text)], "그물 얘기할 때 뭐라고 했지?", NAMES, 10, False)
    assert len(picked) == 2 and picked[0].revision_id != picked[1].revision_id  # one line holds both counts
    apart = pick([_msg(8, text)], "그물 얘기할 때 뭐라고 했지?", NAMES, 10, False)
    assert sorted(q.words for q in apart) == ["그물은 내가 말린다.", "그물이 무겁다."]  # far apart: two lines


def test_the_user_speaks_as_the_persona_and_an_unclear_line_names_nobody():
    [mine] = pick([_msg(2, '"등대까지 같이 가요."', role="user", name="한솔")], "내가 등대 얘기할 때 뭐라고 했지?", NAMES, 5, False)
    assert mine.speaker == "한솔"
    [unclear] = pick([_msg(3, '"등대는 멀다." 류진이 웃자 백도가 고개를 끄덕였다.')], "등대 얘기할 때 뭐라고 했어?", NAMES, 5,
                     False)
    assert unclear.speaker is None  # two subjects: no guess
    [said] = pick([_msg(4, '"등대는 가깝다." 백도가 류진에게 말했다.')], "등대 얘기할 때 뭐라고 했어?", NAMES, 5, False)
    assert said.speaker == "백도"


def test_only_the_quotes_own_sentence_names_the_speaker():
    [listener] = pick([_msg(5, '"등대까지는 내가 노를 젓지." 류진이 말없이 그를 보았다.')], "등대 얘기할 때 뭐라고 했어?",
                      NAMES, 9, False)
    assert listener.speaker is None  # a look is no verb of speaking: the listener, not the speaker
    [nearest] = pick([_msg(6, '한솔이 웃자 늙은 선원이 "등대는 저쪽이다" 하고 손을 들었다.')], "등대 얘기할 때 뭐라고 했어?",
                     NAMES, 9, False)
    assert nearest.speaker is None  # the nearest subject is no known character: none rather than 한솔
    [quoted] = pick([_msg(7, '부두 끝에서 백도가 "등대 불 켜라!" 하고 소리쳤다.')], "등대 얘기할 때 뭐라고 했어?", NAMES, 9, False)
    assert quoted.speaker == "백도"


def test_what_the_question_says_the_words_did_breaks_a_tie():
    # every line holds 등대 in its words: a tie the first line would win
    text = ('"등대는 언제 켜져요." 류진이 말했다. "등대는 몇 시에 켜지니?" 백도가 물었다. '
            '"등대는 해가 지면 켜져." 류진이 대답했다.')
    [asked, *_] = pick([_msg(5, text)], "등대 얘기 때 뭐라고 물었어?", NAMES, 9, False)
    assert asked.words == "등대는 몇 시에 켜지니?"
    [answered, *_] = pick([_msg(5, text)], "등대 얘기 때 뭐라고 대답했어?", NAMES, 9, False)
    assert answered.words == "등대는 해가 지면 켜져."


def test_the_sentence_before_a_quote_counts_as_near():
    # 달력 is in both lines; it sets the scene for the second quote only
    text = '"오늘은 쉰다." 백도가 말했다. 바람이 불었다. 파도가 쳤다. 류진이 달력을 펼쳤다. "하루라도 늦으면 다 밀린다."'
    [top, *_] = pick([_msg(5, text)], "달력 볼 때 뭐라고 했지?", NAMES, 9, False)
    assert top.words == "하루라도 늦으면 다 밀린다."
