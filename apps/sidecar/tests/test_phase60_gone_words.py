"""PHASE-60 S3 (ADR 0082): pure word rule for a character who is gone."""

from __future__ import annotations

import unicodedata

import pytest

from nmos_sidecar.gone import (
    GONE_EN,
    GONE_KO,
    NEAR_MISS,
    NOT_PLACES,
    RECOVERED_EN,
    RECOVERED_KO,
    is_gone_place,
    is_gone_status,
)


def test_packet_v20_constants_are_defined():
    assert set(GONE_KO) == {"사망", "죽음", "죽었", "전사", "실종", "행방불명", "떠남", "추방"}
    assert set(GONE_EN) == {"dead", "killed", "deceased", "missing", "vanished", "departed for good", "exiled"}
    assert set(RECOVERED_KO) == {"회복", "생존", "귀환", "부활"}
    assert set(RECOVERED_EN) == {"recovered", "returned", "alive", "revived"}
    assert {"죽지 않", "죽을 뻔", "죽은 척", "not dead", "nearly died", "presumed"} <= set(NEAR_MISS)
    assert {"행방불명", "실종", "저승", "사후세계", "missing", "the afterlife", "afterlife"} <= set(NOT_PLACES)


@pytest.mark.parametrize(
    "status",
    [
        "전투 중 전사",
        "사망",
        "죽음",
        "죽었다",
        "행방불명 상태",
        "실종됨",
        "마을을 떠남",
        "왕국에서 추방됨",
        "dead",
        "killed in the fire",
        "deceased",
        "missing",
        "vanished without a trace",
        "departed for good",
        "exiled",
    ],
)
def test_gone_statuses_match(status: str):
    assert is_gone_status(status) is True


@pytest.mark.parametrize(
    "status",
    [
        "죽지 않았다",
        "죽을 뻔했다",
        "죽은 척하고 있다",
        "죽은 줄 알았다",
        "실종되지 않았다",
        "not dead",
        "nearly died",
        "presumed dead",
        "no longer missing",
        "departed",
        "회복 중",
        "기적적으로 생존",
        "귀환함",
        "부활했다",
        "returned alive",
        "recovered",
        "전사했지만 부활",
        "",
        None,
        "피곤함",
    ],
)
def test_non_gone_negated_near_miss_and_recovered_statuses_are_false(status: str | None):
    assert is_gone_status(status) is False


@pytest.mark.parametrize(
    "status",
    [
        "  DEAD  ",
        "Departed   For\tGood",
        unicodedata.normalize("NFD", "사망"),
        unicodedata.normalize("NFD", "왕국에서 추방됨"),
        "missing, body unrecovered",
        "실종되어 돌아오지 않음",
    ],
)
def test_gone_status_normalization_and_boundaries_true(status: str):
    assert is_gone_status(status) is True


@pytest.mark.parametrize(
    "status",
    [
        "deadly wound",
        "undead",
        "skilled archer",
        "dismissing the guard",
        "not missing",
        "never exiled",
        "nearly killed",
        "almost dead",
        "not departed for good",
        "isn't dead",
        "dead, then revived",
        "missing, returned",
        "사망 후 회복",
        "실종 후 귀환",
        "사망하지 않음",
        "사망이 아니다",
        "사망할 뻔했다",
        "사망한 척했다",
        "실종된 줄 알았다",
        "사망인 줄 알았다",
        "전사한 줄 알았다",
        "추방당한 줄 알았다",
        "안 죽었다",
        unicodedata.normalize("NFD", "실종되지 않았다"),
    ],
)
def test_gone_status_negations_beliefs_and_word_boundaries_false(status: str):
    assert is_gone_status(status) is False


@pytest.mark.parametrize(
    "place",
    [
        "저승",
        "사후세계",
        "행방불명",
        "실종",
        "the afterlife",
        "afterlife",
        "missing",
        "  The  Afterlife ",
        "AFTERLIFE",
        "MISSING",
        unicodedata.normalize("NFD", "저승"),
    ],
)
def test_gone_places_match_whole_name(place: str):
    assert is_gone_place(place) is True


@pytest.mark.parametrize(
    "place",
    [
        "죽음의 숲",
        "실종자 수색 본부",
        "저승길 주막",
        "missing persons bureau",
        "afterlife tavern",
        "",
        None,
    ],
)
def test_real_places_containing_gone_words_are_false(place: str | None):
    assert is_gone_place(place) is False
