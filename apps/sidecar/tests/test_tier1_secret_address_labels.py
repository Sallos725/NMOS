"""A conditional form of address's label (PHASE-64, ADR 0091) in a secret's head (review of fde34aa, findings 2 and 3).
Pure: no database. Synthetic names and text only."""

from __future__ import annotations

from nmos_sidecar.secrets import _split, matches, reveal_value, secret_text
from test_tier1_secrets_facts_repairs import kept, learned, secrets_of


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


# Finding 2: the label is not part of the object's name; the slot is compared apart, as Phase 64 folds slots. A reveal
# is text, and a `when` phrase does not say whether it was a public, private or situational form's: against a public or
# private secret of the listed turn, a phrase worded anew is that secret only when it is the one such secret there
# (owner decision 2026-11-25). With two, neither ends (fail-safe: it stays hidden; a repair can end it).
def said(pos: int, when: str | None, scope: str = "private", value: str = "오빠") -> dict:
    return kept(pos, "하나", "addresses", "타쿠", value, address_condition={"scope": scope, "when": when})


def reveal(turn: int, when: str | None, scope: str = "private", at: int = 9, value: str = "오빠") -> dict:
    return learned(at, reveal_value({"turn": turn, "text": secret_text(said(turn, when, scope, value))}))


def test_a_reworded_label_ends_the_one_secret_of_its_slot_in_the_listed_turn():
    # listed as "둘만 있을 때", the turn extracted again as "단둘이 있을 때": the one private form of the pair there
    got, unmatched = secrets_of([said(3, "단둘이 있을 때"), reveal(3, "둘만 있을 때")])
    assert got == {"하나 addresses 타쿠 [단둘이 있을 때]: 오빠": []} and unmatched == []
    # a scope's own label and a phrase of that scope, either way round
    got, _ = secrets_of([said(3, None), reveal(3, "둘만 있을 때")])
    assert got == {"하나 addresses 타쿠 [in private]: 오빠": []}
    got, _ = secrets_of([said(3, "단둘이 있을 때"), reveal(3, None)])
    assert got == {"하나 addresses 타쿠 [단둘이 있을 때]: 오빠": []}


def test_a_reworded_label_with_two_candidates_ends_neither():
    rows = [said(3, "사람들 앞에서", "public", "선배님"), said(3, "단둘이 있을 때", "private"), reveal(3, "둘만 있을 때")]
    got, unmatched = secrets_of(rows)
    assert got == {"하나 addresses 타쿠 [사람들 앞에서]: 선배님": ["노엘"], "하나 addresses 타쿠 [단둘이 있을 때]: 오빠": ["노엘"]}
    assert [u["turn"] for u in unmatched] == [9]
    # a label as listed still finds its own slot beside the other one
    rows[-1] = reveal(3, "단둘이 있을 때")
    got, unmatched = secrets_of(rows)
    assert got == {"하나 addresses 타쿠 [사람들 앞에서]: 선배님": ["노엘"], "하나 addresses 타쿠 [단둘이 있을 때]: 오빠": []}
    assert unmatched == []


def test_a_scopes_label_never_matches_the_other_scope():
    for mine, theirs in (("public", "private"), ("private", "public")):
        got, unmatched = secrets_of([said(3, None, mine), reveal(3, None, theirs)])
        assert list(got.values()) == [["노엘"]] and len(unmatched) == 1
        assert not matches(secret_text(said(3, None, mine)), reveal(3, None, theirs)["value"])
    # nor does a phrase worded anew end a secret of another turn (the content rule stays strict)
    got, unmatched = secrets_of([said(6, "단둘이 있을 때"), reveal(3, "둘만 있을 때", at=9)])
    assert list(got.values()) == [["노엘"]] and len(unmatched) == 1
    # A known limit: a phrase does not say its scope, so the one public form of the listed turn is its candidate
    # (rule 1), the private one of another turn is not
    got, _ = secrets_of([said(3, "사람들 앞에서", "public"), said(6, "단둘이 있을 때"), reveal(3, "둘만 있을 때", at=9)])
    assert got == {"하나 addresses 타쿠 [사람들 앞에서]: 오빠": [], "하나 addresses 타쿠 [단둘이 있을 때]: 오빠": ["노엘"]}


def test_a_situational_label_needs_the_same_when_as_phase_64_folds_it():
    got, _ = secrets_of([said(3, "당황했을 때", "situational"), reveal(3, "당황했을  때", "situational")])
    assert list(got.values()) == [[]]  # spacing and case apart, the same `when`
    got, _ = secrets_of([said(3, "When Flustered", "situational"), reveal(3, "when flustered", "situational")])
    assert list(got.values()) == [[]]
    got, unmatched = secrets_of([said(3, "당황했을 때", "situational"), reveal(3, "놀랐을 때", "situational")])
    assert list(got.values()) == [["노엘"]] and len(unmatched) == 1  # another `when` is another slot
    # nor is a situational form's phrase any scope's label
    got, unmatched = secrets_of([said(3, "당황했을 때", "situational"), reveal(3, None)])
    assert list(got.values()) == [["노엘"]] and len(unmatched) == 1


def test_a_secret_without_a_label_is_matched_as_before():
    plain = kept(3, "하나", "addresses", "타쿠", "오빠")
    got, _ = secrets_of([plain, learned(9, reveal_value({"turn": 3, "text": secret_text(plain)}))])
    assert got == {"하나 addresses 타쿠: 오빠": []}
    # by the content rule from another turn too
    assert matches(secret_text(plain), "[turn 1] 하나 addresses 타쿠: 오빠")
    # a condition one side has and the other has not (dropped or added by a re-extraction of the listed turn, or a
    # reveal recorded before extract-v20): the one form of the pair there, as before; never with two, nor from
    # another turn
    got, unmatched = secrets_of([plain, reveal(3, "둘만 있을 때")])
    assert got == {"하나 addresses 타쿠: 오빠": []} and unmatched == []
    got, _ = secrets_of([said(3, "둘만 있을 때"), learned(9, reveal_value({"turn": 3, "text": secret_text(plain)}))])
    assert got == {"하나 addresses 타쿠 [둘만 있을 때]: 오빠": []}
    got, unmatched = secrets_of([plain, said(3, "단둘이 있을 때", value="자기"), reveal(3, "둘만 있을 때")])
    assert set(map(tuple, got.values())) == {("노엘",)} and len(unmatched) == 1
    got, unmatched = secrets_of([said(6, "둘만 있을 때"), learned(9, reveal_value({"turn": 3, "text": secret_text(plain)}))])
    assert list(got.values()) == [["노엘"]] and len(unmatched) == 1
