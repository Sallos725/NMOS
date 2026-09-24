"""Phase 6 (docs/phases/PHASE-6.md): an item's holder and place are one whereabouts (Q2)."""

from __future__ import annotations

from test_semantics import current, row


def item_at(pos: int, item: str, place: str, **kw):
    return row(pos, item, "located_in", place, subject_type="item", **kw)


def held(pos: int, who: str, item: str, **kw):
    return row(pos, who, "possesses", item, **kw)


def test_a_newer_place_closes_the_holder():
    assert current([held(1, "하나", "지도"), item_at(3, "지도", "탁자")]) == [("지도", "탁자", "positive")]


def test_a_newer_holder_closes_the_place():
    assert current([item_at(1, "지도", "탁자"), held(3, "카이토", "지도")]) == [("카이토", "지도", "positive")]


def test_holder_and_place_from_one_turn_stay_together():
    assert current([held(2, "하나", "지도"), item_at(2, "지도", "도서관")]) == [
        ("하나", "지도", "positive"), ("지도", "도서관", "positive")]
    # A later turn that moves the item keeps only what it states.
    assert current([held(2, "하나", "지도"), item_at(2, "지도", "도서관"), item_at(4, "지도", "항구")]) == [
        ("지도", "항구", "positive")]


def test_negations_end_only_their_own_slot():
    # "Hana lost the map" ends the holder as before (ADR 0013); a denial of another place changes nothing.
    assert current([held(1, "하나", "지도"), held(2, "하나", "지도", polarity="negative")]) == [
        ("하나", "지도", "negative")]
    assert current([item_at(1, "지도", "탁자"), item_at(2, "지도", "항구", polarity="negative")]) == [
        ("지도", "탁자", "positive"), ("지도", "항구", "negative")]
    # A negation is no statement of where the item is now: it does not close the other slot.
    assert current([item_at(1, "지도", "탁자"), held(2, "하나", "지도", polarity="negative")]) == [
        ("지도", "탁자", "positive"), ("하나", "지도", "negative")]


def test_a_characters_place_is_its_own_fact():
    from nmos_sidecar.facts import version_key
    assert version_key(row(1, "하나", "located_in", "도서관")) == ("located_in", "하나")
    assert version_key(held(1, "하나", "지도")) == version_key(item_at(2, "지도", "탁자")) == ("whereabouts", "지도")


def test_messages_without_a_turn_count_alone():
    # Per-message extractions of older generations: two messages are two statements, not one turn.
    a = {**held(5, "하나", "지도"), "turn": None}
    b = {**item_at(6, "지도", "탁자"), "turn": None}
    assert current([a, b]) == [("지도", "탁자", "positive")]


def test_history_names_each_predicate():
    from nmos_sidecar.facts import _versions
    (fact,) = _versions([held(1, "하나", "지도"), item_at(3, "지도", "탁자")])
    assert [(h["predicate"], h["subject"]) for h in fact["history"]] == [("possesses", "하나"), ("located_in", "지도")]
    assert fact["versions"] == 2
