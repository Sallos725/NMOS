"""PHASE-35: packet-v15 anchors an excerpt on what the question asks, not on when it happened."""

from __future__ import annotations

from nmos_sidecar.keywords import keywords
from nmos_sidecar.packet import POLICIES, anchor_rank, grown_excerpt
from nmos_sidecar.retrieval import FUNCTION_SYLLABLES, anchor_words, one_char_words

SHOP = ("문을 열자 종이 울렸다. 빵집 안은 따뜻했다. 미나가 계산대 뒤에서 고개를 들었다. "
        "\"손님, 이런 질문은 처음 들어봐요.\" 미나가 웃었다. 그녀는 진열대에서 빵 하나를 집었다. "
        "\"그럼 이거 드셔 보세요. 꿀호두 스콘이요.\" 지호는 스콘을 받아 들었다. "
        "\"그럼 이 동네 첫 빵이 제 스콘이네요.\" 지호는 한 입 베어 물었다.")

HARBOUR = ("안개가 부두를 덮었다. 항구에 온 지 사흘, 부딪히는 것마다 벽이었다. 지호는 난간에 기대 섰다. "
           "그때 안개가 걷혔다. 지호는 한참 동안 넋을 놓고 푸른 달을 바라보았다. 바다가 조용했다.")


def ask(query: str) -> tuple[list[str], tuple[str, ...]]:
    return anchor_words(query, keywords(query), one_char_words(query))


def test_packet_v15_is_a_policy():
    assert "packet-v15" in POLICIES


def test_a_first_cue_breaks_ties_instead_of_anchoring():
    words, tie = ask("미나가 처음 권해 준 빵이 뭐였어?")
    assert "처음" not in words and words  # 처음 says when, not what
    assert tie[:2] == ("처음", "첫")  # the story may say 첫 where the question says 처음
    text, _ = grown_excerpt(SHOP, " ".join(words), words, 120, tie_words=tie)
    assert "스콘" in text
    old, _ = grown_excerpt(SHOP, " ".join(keywords("미나가 처음 권해 준 빵이 뭐였어?")),
                           keywords("미나가 처음 권해 준 빵이 뭐였어?"), 120, tie_words=one_char_words("미나가 처음 권해 준 빵이 뭐였어?"))
    assert "처음 들어봐요" in old  # packet-v14: anchored on 처음


def test_one_syllable_function_words_no_longer_break_ties():
    q = "지호가 항구에 온 지 얼마 안 됐을 때 밤하늘에 떴던 달 기억나?"
    words, tie = ask(q)
    assert tie == ("달",) and not set(tie) & FUNCTION_SYLLABLES
    text, _ = grown_excerpt(HARBOUR, " ".join(words), words, 60, tie_words=tie)
    assert "푸른 달" in text


def test_a_question_without_a_cue_keeps_its_words():
    q = "이안이 빌려준 책 제목이 뭐였지?"
    words, tie = ask(q)
    assert words == keywords(q) and tie == ("책",)  # PHASE-31's one-character noun still breaks a tie


def test_the_whole_message_replaces_a_chunk_that_says_less_of_what_the_question_names():
    words, tie = ask("지호가 항구에 온 지 얼마 안 됐을 때 밤하늘에 떴던 달 기억나?")
    chunk = HARBOUR[: HARBOUR.index("그때")]
    assert anchor_rank(HARBOUR, ("달",), words) > anchor_rank(chunk, ("달",), words)
    assert anchor_rank("", ("달",), words) == (0, 0)
