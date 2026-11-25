"""A conditional form of address's label (PHASE-64, ADR 0091) in a secret's head (review of fde34aa, findings 2 and 3).
Pure: no database. Synthetic names and text only."""

from __future__ import annotations

from nmos_sidecar.secrets import _split, matches, reveal_value, secret_text


def address(when: str | None, scope: str = "private", value: str = "오빠", turn: int = 3) -> dict:
    return {"subject": "하나", "predicate": "addresses", "object": "타쿠", "value": value, "turn": turn,
            "address_condition": {"scope": scope, "when": when}}


# Finding 3: ": " inside `when`. The head ends at the label's "]: "; nothing stored changes.
def test_a_label_holding_a_colon_stays_in_the_head():
    text = secret_text(address("임무 중: 변장했을 때"))
    assert text == "하나 addresses 타쿠 [임무 중: 변장했을 때]: 오빠"  # what is listed and stored, as before
    assert _split(text) == (None, "하나 addresses 타쿠 [임무 중: 변장했을 때]", "오빠")
    assert _split(reveal_value({"turn": 3, "text": text})) == (3, "하나 addresses 타쿠 [임무 중: 변장했을 때]", "오빠")
    assert matches(text, reveal_value({"turn": 3, "text": text}))


def test_a_label_without_a_colon_splits_as_before():
    text = secret_text(address("둘만 있을 때"))
    assert _split(text) == (None, "하나 addresses 타쿠 [둘만 있을 때]", "오빠")


def test_a_bracket_and_colon_elsewhere_split_as_before():
    # not an `addresses` head: the first ": " still ends it
    assert _split("하나 goal: [지도]: 찾기") == (None, "하나 goal", "[지도]: 찾기")
    assert _split("하나 [가면] knows: 비밀: 하나") == (None, "하나 [가면] knows", "비밀: 하나")
    # an unlabelled `addresses` whose value holds "[x]: "
    assert _split("하나 addresses 타쿠: [농담]: 오빠") == (None, "하나 addresses 타쿠", "[농담]: 오빠")
