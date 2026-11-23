"""PHASE-60 S3 (ADR 0082): pure word rule for a character who is gone."""

from __future__ import annotations

import unicodedata

import pytest

from nmos_sidecar.gone import (
    GONE_EN,
    GONE_KO,
    ALIVE_EN,
    ALIVE_KO,
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


@pytest.mark.parametrize(
    "status",
    [
        "전사했다",
        "사망함",
        "죽었음",
        "죽음.",
        "추방당함",
        "dead.",
        "missing since the storm",
        "exiled from the kingdom",
        "killed by poison",
        "vanished during the night",
        "vanished for good",
    ],
)
def test_gone_whole_words_in_state_still_match(status: str):
    assert is_gone_status(status) is True


@pytest.mark.parametrize(
    "status",
    [
        "여전사처럼 싸우는 중",
        "죽음을 두려워함",
        "죽음의 공포에 떨고 있음",
        "죽음이 다가오는 걸 느낌",
        "실종자를 찾는 중",
        "사망률이 높은 병에 걸림",
        "missing her family",
        "missing home",
        "dead tired",
        "dead set on revenge",
        "dead serious",
        "사망에 대한 기록",
        "실종을 우려함",
        "전사를 꿈꿈",
        "missing attention",
        "dead inside",
    ],
)
def test_gone_topics_compounds_and_idioms_are_false(status: str):
    assert is_gone_status(status) is False


def test_alive_words_outside_the_recovered_list_are_defined():
    assert set(ALIVE_KO) == {"살아", "발견"}
    assert set(ALIVE_EN) == {"living", "found", "back from"}
    assert {"직전", "위기", "추정", "알려", "소문", "생각", "처리"} <= set(NEAR_MISS)
    assert {"rumored", "rumoured", "believed", "thought", "reportedly"} <= set(NEAR_MISS)


@pytest.mark.parametrize(
    "status",
    [
        "사망",
        "사망함",
        "사망한",
        "사망한 상태",
        "사망한 것으로 확인됨",
        "실종된 채로 발견되지 않음",
        "죽음",
        "죽었다",
        "전사함",
        "전사했다",
        "전장에서 전사",
        "실종",
        "실종됨",
        "실종된 지 3년",
        "행방불명",
        "떠남",
        "영영 떠남",
        "영원히 마을을 떠남",
        "추방됨",
        "dead",
        "killed",
        "deceased",
        "missing",
        "is missing",
        "went missing",
        "still missing",
        "has been missing since the storm",
        "vanished",
        "exiled",
        "departed for good",
        "found dead in the river",
    ],
)
def test_plain_gone_statuses_stay_true(status: str):
    """The subject itself is plainly dead, missing or gone for good, now."""
    assert is_gone_status(status) is True


@pytest.mark.parametrize(
    "status",
    [
        "죽음 직전",
        "죽음 직전까지 갔다",
        "사망 직전",
        "사망 추정",
        "실종 위기",
        "죽었다고 알려짐",
        "죽었다는 소문이 돎",
        "죽었다고 생각했지만 살아 있음",
        "사망 처리됨 (실제로는 살아 있음)",
        "사망했다고 함",
        "실종 상태로 알려짐",
        "사망 소문이 돎",
        "사망한 것으로 생각됨",
        "사망 처리됨",
        "rumored dead",
        "rumoured to be dead",
        "believed killed",
        "thought dead",
        "reportedly killed",
    ],
)
def test_near_death_presumed_rumoured_and_believed_are_false(status: str):
    assert is_gone_status(status) is False


@pytest.mark.parametrize(
    "status",
    [
        "동생이 실종됨",
        "아버지가 사망함",
        "아버지가 전사한 뒤 슬픔에 잠김",
        "동생은 실종됨",
        "어머니께서 돌아가신 뒤 사망 소식에 충격",
        "실종된 동생을 찾는 중",
        "사망한 아버지를 그리워함",
        "추방된 왕자를 따름",
        "her brother was killed",
        "mourning her father, who is dead",
        "grieving because her brother is missing",
        "searching for her sister, missing since the storm",
        "the village elder is dead",
    ],
)
def test_someone_elses_fate_in_the_subjects_status_is_false(status: str):
    assert is_gone_status(status) is False


@pytest.mark.parametrize("status", ["전사", "숙련된 전사", "용맹한 전사", "전사 계급", "전사다", "전사의 길을 걸음"])
def test_jeonsa_as_warrior_is_false(status: str):
    assert is_gone_status(status) is False


@pytest.mark.parametrize("status", ["left arm missing", "one eye missing", "wallet missing", "missing an arm"])
def test_a_missing_object_or_body_part_is_false(status: str):
    assert is_gone_status(status) is False


@pytest.mark.parametrize(
    "status",
    [
        "마을을 떠남",
        "잠시 마을을 떠남",
        "출장으로 마을을 떠남",
        "집을 떠남",
        "잠깐 떠남",
        "여행을 떠남",
        "exiled from the court but living in the capital",
    ],
)
def test_a_leave_that_is_not_plainly_for_good_is_false(status: str):
    assert is_gone_status(status) is False


@pytest.mark.parametrize(
    "status",
    [
        "살아 있음, 한때 실종됨",
        "살아 돌아옴",
        "실종됐다가 발견됨",
        "실종 후 발견됨",
        "found after going missing",
        "missing, found in the woods",
        "back from the dead",
    ],
)
def test_returned_in_words_outside_the_recovered_list_is_false(status: str):
    assert is_gone_status(status) is False


@pytest.mark.parametrize("status", ["실종 후 발견되지 않음", "missing, never found", "missing, not found"])
def test_not_found_is_no_return(status: str):
    assert is_gone_status(status) is True
