"""PHASE-60 S8 (ADR 0087): pure @name mention parser for per-request character pinning."""

from __future__ import annotations

from nmos_sidecar.mentions import at_mentions
from nmos_sidecar.scene import PERSONA


def test_basic_mentions_and_trailing_korean_particles():
    names = {"세라": "세라", "카이토": "카이토", "하나": "하나"}
    assert at_mentions("@세라 어디 있어?", names) == ["세라"]
    assert at_mentions("@세라 카이토 어디 있어?", names) == ["세라"]
    assert at_mentions("@세라는 뭐 해", names) == ["세라"]
    assert at_mentions("@카이토에게 말해", names) == ["카이토"]
    assert at_mentions("(@하나) 봐", names) == ["하나"]


def test_at_inside_word_email_or_unknown_name_does_nothing():
    names = {"세라": "세라", "example": "example", "bar": "bar", "host": "host"}
    assert at_mentions("메일은 sera@example.com", names) == []
    assert at_mentions("foo@세라", names) == []
    assert at_mentions("a@b.com user@host foo@bar", names) == []
    assert at_mentions("foo_@세라 foo-@세라 foo.@세라 123@세라", names) == []
    assert at_mentions("@없는이름", names) == []


def test_order_and_deduplication():
    names = {"세라": "세라", "카이토": "카이토", "하나": "하나"}
    assert at_mentions("@세라 @카이토 둘 다", names) == ["세라", "카이토"]
    assert at_mentions("@카이토 @세라 순서 유지", names) == ["카이토", "세라"]
    assert at_mentions("@세라 @세라", names) == ["세라"]
    assert at_mentions("@세라 @카이토 @세라는", names) == ["세라", "카이토"]


def test_blocked_persona_and_excluded_characters():
    names = {"타쿠미": PERSONA, "세라": "ent-sera", "하나": "ent-hana"}
    assert at_mentions("@타쿠미 어디 있어?", names, blocked={PERSONA}) == []
    assert at_mentions("@타쿠미 @세라 @하나", names, blocked={PERSONA, "ent-hana"}) == ["ent-sera"]


def test_alias_keys_and_deduplication_by_resolved_key():
    names = {
        "세라": "ent-sera",
        "세라쨩": "ent-sera",
        "붉은 마녀": "ent-sera",
        "kaito": "ent-kaito",
    }
    assert at_mentions("@세라쨩 이리 와", names) == ["ent-sera"]
    assert at_mentions("@세라 @세라쨩", names) == ["ent-sera"]
    assert at_mentions("@붉은 마녀에게 물어봐", names) == ["ent-sera"]
    assert at_mentions("@Kaito에게 전해", names) == ["ent-kaito"]


def test_multi_word_name_with_and_without_particle():
    names = {"아오키 타쿠미": "아오키 타쿠미", "세라": "세라"}
    assert at_mentions("@아오키 타쿠미에게", names) == ["아오키 타쿠미"]
    assert at_mentions("@아오키 타쿠미 여기야!", names) == ["아오키 타쿠미"]
    assert at_mentions("(@아오키 타쿠미) 봐", names) == ["아오키 타쿠미"]
    assert at_mentions("@아오키 어디 있어?", names) == []
    # Do not join across a line break.
    assert at_mentions("@아오키\n타쿠미에게", names) == []


def test_multi_word_prefers_full_name_and_respects_blocked():
    names = {"아오키": "ent-aoki", "아오키 타쿠미": PERSONA}
    assert at_mentions("@아오키 타쿠미에게", names, blocked={PERSONA}) == []
    assert at_mentions("@아오키에게", names, blocked={PERSONA}) == ["ent-aoki"]


def test_bare_at_and_space_after_at():
    names = {"세라": "세라"}
    assert at_mentions("@", names) == []
    assert at_mentions("@ 세라", names) == []
    assert at_mentions("@@세라", names) == []
    assert at_mentions("", names) == []
    assert at_mentions("@세라", {}) == []


def test_allowed_opening_and_closing_punctuation():
    names = {"하나": "하나", "유나": "유나"}
    for text in (
        "[@하나]",
        "{@하나}",
        '"@하나"',
        "'@하나'",
        "“@하나”",
        "‘@하나’",
        "「@하나」",
        "『@하나』",
        "안녕,@하나!",
        "어디?@하나…",
        "잠깐!@하나: 여기",
        "음…@하나;",
    ):
        assert at_mentions(text, names) == ["하나"], text
    assert at_mentions("「@하나」, 「@유나」", names) == ["하나", "유나"]


def test_particle_stripping_longest_first_and_only_once():
    names = {"세라": "세라", "소로": "소로"}
    # Longest particle ("에서는") stripped in one step.
    assert at_mentions("@세라에서는 무슨 일이", names) == ["세라"]
    # Name ending in a syllable of a 2-char particle ("로는") still matches via 1-char particle ("는").
    assert at_mentions("@소로는 괜찮아", names) == ["소로"]
    # Only ONE trailing particle is stripped ("에게만" is not a single particle in keywords._SOURCE_PARTICLES).
    assert at_mentions("@세라에게만 말해", names) == []
