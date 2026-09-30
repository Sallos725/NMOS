"""PHASE-18 Q1 (ADR 0052): the words of a user message that are looked up on their own. Pure."""

from nmos_sidecar.keywords import KEYWORDS_MAX, keywords


def test_particles_and_question_endings_come_off_and_question_words_go():
    assert keywords("무진 선장 앵무새 이름이 뭐였더라?") == ["앵무새", "무진", "선장", "이름"]
    assert keywords("이안 책상 위 모래시계 모래는 무슨 색이었지?")[:2] == ["모래시계", "이안"]
    assert keywords("하람이랑 지금 어떤 사이야?") == ["하람"]  # 사이 and 지금 are stop words; 어떤 a question word


def test_a_name_an_ending_rule_would_shorten_keeps_its_form():
    assert keywords("민지 어디?") == ["민지"]  # not 민 (-지)
    assert keywords("사과는 누가 먹었어?")[:2] == ["사과", "사과는"]  # not 사 (-과); 먹었어 says what happened
    assert keywords("하나는 지금 뭐 해?") == ["하나", "하나는"]  # -나 is not taken off 하나


def test_a_one_syllable_particle_keeps_the_word_as_a_fallback():
    assert keywords("서도윤이 웃었다") == ["서도윤", "서도윤이", "웃었다"]  # the verb last, room permitting


def test_verbs_come_after_names_and_nouns():
    assert keywords("게이트 끝나고 마정석 팔아서 받았어?")[:2] == ["게이트", "마정석"]


def test_at_most_four_longest_first():
    words = keywords("등대지기 자장가 청새치호 은빛잉크 바람결 지도방")
    assert len(words) == KEYWORDS_MAX and words[0] in ("등대지기", "청새치호", "은빛잉크")


def test_latin_numbers_and_stop_words():
    assert keywords("What did Kaito say about the letter?") == ["letter", "kaito", "say"]
    assert keywords("3 더하기 5는?") == ["더하기"]
    assert keywords("뭐? 왜? 지금?") == []
    assert keywords("") == []
